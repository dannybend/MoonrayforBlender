# SPDX-License-Identifier: GPL-3.0-or-later
#
# MoonRay RenderEngine: final render (F12) and interactive viewport rendering,
# like Cycles.

import time

import bpy
import gpu
from gpu_extras.presets import draw_texture_2d

from . import bridge_process
from .client import BridgeClient, BridgeError
from .export import camera as cam_export
from .export.scene import SceneSync
from .preferences import get_prefs

# Blender device -> MoonRay execution mode. XPU (GPU) falls back to CPU on
# its own when the scene uses features the GPU path doesn't support.
_EXEC_MODES = {'CPU': "vectorized", 'GPU': "xpu"}


def _connect(scene, fps):
    prefs = get_prefs()
    bridge_process.ensure_running(prefs)
    client = BridgeClient(prefs.host, prefs.port)
    client.connect()
    client.hello(threads=scene.moonray.threads, fps=fps, exec_mode=_EXEC_MODES[scene.moonray.device])
    return client


def _dirty_geometry(depsgraph):
    """Names of original objects whose geometry changed in this update."""
    dirty = set()
    meshes = set()
    for update in depsgraph.updates:
        id_ = update.id
        if isinstance(id_, bpy.types.Object):
            if update.is_updated_geometry:
                dirty.add(id_.original.name_full)
        elif isinstance(id_, (bpy.types.Mesh, bpy.types.Curve, bpy.types.MetaBall)):
            meshes.add(id_.original.name_full)
    if meshes:
        for obj in depsgraph.objects:
            if obj.data is not None and obj.data.original.name_full in meshes:
                dirty.add(obj.original.name_full)
    return dirty


class _ViewportDraw:
    """Texture holding the latest viewport frame."""

    def __init__(self):
        self.texture = None

    def update(self, frame):
        buffer = gpu.types.Buffer('FLOAT', frame.width * frame.height * 4, frame.pixels)
        self.texture = gpu.types.GPUTexture((frame.width, frame.height), format='RGBA32F', data=buffer)

    def draw(self, width, height):
        if self.texture is not None:
            draw_texture_2d(self.texture, (0, 0), width, height)


class _ViewportSession:
    def __init__(self, scene):
        self.client = _connect(scene, fps=scene.moonray.viewport_fps)
        self.device = scene.moonray.device
        self.sync = SceneSync(self.client, viewport=True)
        self.draw_data = _ViewportDraw()
        self.initialized = False
        self.progress = 0.0

    def close(self):
        self.client.close()


class MoonRayRenderEngine(bpy.types.RenderEngine):
    bl_idname = "MOONRAY"
    bl_label = "MoonRay"
    bl_use_preview = False
    bl_use_eevee_viewport = True       # "Material Preview" uses EEVEE
    bl_use_shading_nodes_custom = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._viewport = None
        self._viewport_error = None

    def __del__(self):
        viewport = getattr(self, "_viewport", None)
        if viewport is not None:
            try:
                viewport.close()
            except Exception:
                pass

    # -- Final render (F12) ------------------------------------------------

    def render(self, depsgraph):
        scene = depsgraph.scene
        render = scene.render
        scale = render.resolution_percentage / 100.0
        width = int(render.resolution_x * scale)
        height = int(render.resolution_y * scale)

        if scene.camera is None:
            self.report({'ERROR'}, "The scene has no active camera")
            return

        self.update_stats("", "MoonRay: connecting to the bridge")
        try:
            client = _connect(scene, fps=2.0)
        except (BridgeError, RuntimeError) as e:
            self.report({'ERROR'}, str(e))
            return

        try:
            self.update_stats("", "MoonRay: exporting scene")
            camera = cam_export.from_scene_camera(depsgraph, scene.camera, width, height)
            SceneSync(client, viewport=False).sync(depsgraph, camera, width, height)
            client.start()

            result = self.begin_result(0, 0, width, height)
            combined = result.layers[0].passes["Combined"]
            started = time.monotonic()
            self.update_stats("", "MoonRay: preparing render")

            while True:
                if self.test_break():
                    client.stop()
                    break
                frame = client.wait_frame(0.25)
                if frame is not None:
                    if (frame.width, frame.height) == (width, height):
                        combined.rect.foreach_set(frame.pixels)
                        self.update_result(result)
                    self.update_progress(frame.progress)
                    elapsed = time.monotonic() - started
                    self.update_stats("", f"MoonRay: {frame.progress * 100:.0f}% | {elapsed:.1f} s")
                    if frame.complete:
                        break
                if client.errors:
                    self.report({'ERROR'}, client.errors[-1])
                    if not client.connected:
                        break
                    client.errors.clear()
                if not client.connected:
                    break

            self.end_result(result)
        finally:
            client.close()

    # -- Viewport ----------------------------------------------------------

    def _viewport_size(self, context):
        divider = int(context.scene.moonray.viewport_resolution)
        region = context.region
        return max(1, region.width // divider), max(1, region.height // divider)

    def _sync_viewport(self, context, depsgraph, dirty, view_only=False):
        session = self._viewport
        width, height = self._viewport_size(context)
        camera = cam_export.from_viewport(context)
        if view_only:
            changed = session.sync.sync_view(depsgraph.scene, camera, width, height)
        else:
            changed = session.sync.sync(depsgraph, camera, width, height, dirty)
        if changed or not session.initialized:
            session.client.start()
            session.initialized = True

    def view_update(self, context, depsgraph):
        # The execution mode is fixed when the RenderContext is created, so
        # switching device requires a new session.
        if self._viewport is not None and self._viewport.device != depsgraph.scene.moonray.device:
            self._viewport.close()
            self._viewport = None
        if self._viewport is None:
            try:
                self._viewport = _ViewportSession(depsgraph.scene)
                self._viewport_error = None
            except (BridgeError, RuntimeError) as e:
                self._viewport_error = str(e)
                print("[MoonRay]", e)
                return
            dirty = None
        else:
            dirty = _dirty_geometry(depsgraph)
        try:
            self._sync_viewport(context, depsgraph, dirty)
        except (BridgeError, OSError) as e:
            self._viewport_error = str(e)
            print("[MoonRay]", e)

    def view_draw(self, context, depsgraph):
        session = self._viewport
        if session is None or not session.client.connected:
            if self._viewport_error:
                self.update_stats("", "MoonRay: " + self._viewport_error)
            return

        # View changes (orbit, zoom, window size) arrive here, not in
        # view_update.
        try:
            self._sync_viewport(context, depsgraph, dirty=None, view_only=True)
        except (BridgeError, OSError) as e:
            print("[MoonRay]", e)
            return

        frame = session.client.take_frame()
        if frame is not None:
            session.draw_data.update(frame)
            session.progress = frame.progress

        scene = depsgraph.scene
        gpu.state.blend_set('ALPHA_PREMULT')
        self.bind_display_space_shader(scene)
        session.draw_data.draw(context.region.width, context.region.height)
        self.unbind_display_space_shader()
        gpu.state.blend_set('NONE')

        if session.client.errors:
            self.update_stats("", "MoonRay: " + session.client.errors[-1])
        elif session.client.complete:
            self.update_stats("", "MoonRay: done")
        else:
            self.update_stats("", f"MoonRay: {session.progress * 100:.0f}%")
            # Keep requesting redraws while the render converges
            self.tag_redraw()


classes = (MoonRayRenderEngine,)
