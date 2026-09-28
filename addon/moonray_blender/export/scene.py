# SPDX-License-Identifier: GPL-3.0-or-later
#
# Incremental synchronization of the Blender scene with MoonRay.
#
# SceneSync remembers the RDLA text it already sent for each object and only
# resends what changed. Meshes (the expensive part) are only resent when
# Blender reports a geometry change. If the set of assigned objects, lights or
# materials changes, the Layer, GeometrySet and LightSet are emptied and rebuilt.

import os
import tempfile

import bpy

from .. import protocol as P
from . import camera as cam_export
from . import lights as light_export
from . import materials as mat_export
from . import rdla
from .mesh import mesh_payload

LAYER = "/blender/layer"
GEOMETRY_SET = "/blender/geometryset"
LIGHT_SET = "/blender/lightset"

GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}


def windows_to_wsl(path):
    """C:\\folder\\tex.png -> /mnt/c/folder/tex.png"""
    path = os.path.normpath(path)
    if len(path) >= 2 and path[1] == ":":
        rest = path[2:].replace("\\", "/")
        return f"/mnt/{path[0].lower()}{rest}"
    return path.replace("\\", "/")


def _visibility_attrs(obj):
    return {
        "visible_in_camera": rdla.b(obj.visible_camera),
        "visible_shadow": rdla.b(obj.visible_shadow),
        "visible_diffuse_reflection": rdla.b(obj.visible_diffuse),
        "visible_diffuse_transmission": rdla.b(obj.visible_diffuse),
        "visible_glossy_reflection": rdla.b(obj.visible_glossy),
        "visible_glossy_transmission": rdla.b(obj.visible_transmission),
        "visible_mirror_reflection": rdla.b(obj.visible_glossy),
        "visible_mirror_transmission": rdla.b(obj.visible_transmission),
    }


class SceneSync:
    def __init__(self, client, viewport):
        self.client = client
        self.viewport = viewport
        self._sent = {}          # RDL name -> last RDLA text sent
        self._mesh_parts = {}    # geometry name -> [(part, material index)]
        self._lights = {}        # RDL name -> class, of the lights that are on
        self._layout = None
        self._textures = {}
        self._tmpdir = None

    # -- textures ---------------------------------------------------------

    def texture_path(self, image):
        if image.name in self._textures:
            return self._textures[image.name]
        path = None
        if image.packed_file is not None:
            if self._tmpdir is None:
                self._tmpdir = tempfile.mkdtemp(prefix="moonray_tex_")
            ext = os.path.splitext(image.filepath_raw)[1] or ".png"
            path = os.path.join(self._tmpdir, rdla.safe_name(image.name) + ext)
            with open(path, "wb") as fh:
                fh.write(image.packed_file.data)
        elif image.source in {'FILE', 'SEQUENCE', 'TILED'} and image.filepath:
            path = bpy.path.abspath(image.filepath, library=image.library)
        if path is None:
            print(f"[MoonRay] Image '{image.name}' not supported (neither a file nor packed)")
        result = windows_to_wsl(path) if path else None
        self._textures[image.name] = result
        return result

    # -- synchronization ---------------------------------------------------

    def _changed(self, name, text):
        if self._sent.get(name) == text:
            return False
        self._sent[name] = text
        return True

    def sync(self, depsgraph, camera, width, height, dirty_geometry=None):
        """Sends MoonRay what changed. Returns True if anything changed.

        dirty_geometry: names of original objects whose geometry changed;
        None = everything (first sync).
        """
        scene = depsgraph.scene
        out = []                  # RDLA blocks to send
        geometries = []           # (class, name, [(part, material)])
        lights = {}               # name -> class
        materials = {}            # RDL name -> Material
        instance_groups = {}      # key -> [evaluated object, [matrices]]

        def mats_for(obj, parts):
            result = []
            for part, index in parts:
                mat = None
                if index < len(obj.material_slots):
                    mat = obj.material_slots[index].material
                if mat is None:
                    result.append((part, mat_export.DEFAULT_MATERIAL))
                else:
                    name = mat_export.material_name(mat)
                    materials[name] = mat
                    result.append((part, name))
            return result

        def export_mesh(geo_name, obj, force):
            if not force and geo_name in self._mesh_parts:
                return self._mesh_parts[geo_name]
            mesh = obj.to_mesh()
            if mesh is None:
                return None
            try:
                payload, parts = mesh_payload(geo_name, mesh)
            finally:
                obj.to_mesh_clear()
            self.client.send(P.MESH, payload)
            self._mesh_parts[geo_name] = parts
            return parts

        def is_dirty(obj):
            return dirty_geometry is None or obj.original.name_full in dirty_geometry

        for inst in depsgraph.object_instances:
            obj = inst.object
            if obj.type == 'LIGHT':
                key = obj.name_full
                if inst.is_instance:
                    key = f"{inst.parent.name_full}/{key}/{inst.persistent_id[0]}"
                name = light_export.light_name(key)
                obj_for_light = obj
                # Instances share the object but not the matrix
                if inst.is_instance:
                    obj_for_light = _InstanceView(obj, inst.matrix_world)
                cls, text = light_export.light_rdla(name, obj_for_light)
                if text:
                    lights[name] = cls
                    if self._changed(name, text):
                        out.append(text)
                continue

            if obj.type not in GEOMETRY_TYPES or not inst.show_self:
                continue

            if inst.is_instance:
                key = obj.name_full + "|" + (obj.data.name if obj.data else "")
                group = instance_groups.setdefault(key, [obj, []])
                group[1].append(inst.matrix_world.copy())
                continue

            geo_name = "/blender/geo/" + rdla.safe_name(obj.name_full)
            parts = export_mesh(geo_name, obj, is_dirty(obj))
            if parts is None:
                continue
            attrs = {"node_xform": rdla.mat4(obj.matrix_world)}
            attrs.update(_visibility_attrs(obj))
            text = rdla.block("RdlMeshGeometry", geo_name, attrs)
            if self._changed(geo_name + "#xform", text):
                out.append(text)
            geometries.append(("RdlMeshGeometry", geo_name, mats_for(obj, parts)))

        # Instances: a prototype mesh + an RdlInstancerGeometry with matrices
        for key, (obj, matrices) in instance_groups.items():
            safe = rdla.safe_name(key)
            proto = "/blender/proto/" + safe
            parts = export_mesh(proto, obj, is_dirty(obj))
            if parts is None:
                continue
            instancer = "/blender/instancer/" + safe
            text = rdla.block("RdlInstancerGeometry", instancer, {
                "references": "{ " + rdla.ref("RdlMeshGeometry", proto) + " }",
                "method": "2",  # xform list
                "xform_list": "{ " + ", ".join(rdla.mat4(m) for m in matrices) + " }",
            })
            if self._changed(instancer, text):
                out.append(text)
            geometries.append(("RdlMeshGeometry", proto, mats_for(obj, parts)))
            geometries.append(("RdlInstancerGeometry", instancer, [("", mat_export.DEFAULT_MATERIAL)]))

        # Materials
        text = mat_export.default_material_rdla()
        if self._changed(mat_export.DEFAULT_MATERIAL, text):
            out.append(text)
        for name, mat in materials.items():
            text = mat_export.material_rdla(mat, self.texture_path)
            if self._changed(name, text):
                out.append(text)

        # World
        text = light_export.world_rdla(scene.world, self.texture_path)
        if text:
            lights[light_export.WORLD_LIGHT] = "EnvLight"
            if self._changed(light_export.WORLD_LIGHT, text):
                out.append(text)

        # Lights that are gone get switched off
        for name, cls in self._lights.items():
            if name not in lights:
                out.append(light_export.light_off_rdla(cls, name))
                self._sent.pop(name, None)
        self._lights = lights

        out.extend(self._view_blocks(scene, camera, width, height))

        # Layer / GeometrySet / LightSet
        layout = (tuple((c, n, tuple(p)) for c, n, p in geometries), tuple(sorted(lights.items())))
        layout_changed = layout != self._layout
        if layout_changed:
            self._layout = layout

        if out:
            self.client.send_rdla("".join(out))
        if layout_changed:
            for name in (LAYER, GEOMETRY_SET, LIGHT_SET):
                self.client.send(P.CLEAR, name.encode())
            self.client.send_rdla(self._layout_rdla(geometries, lights))

        return bool(out) or layout_changed

    def sync_view(self, scene, camera, width, height):
        """Only camera and resolution (cheap; called on every redraw)."""
        out = self._view_blocks(scene, camera, width, height)
        if out:
            self.client.send_rdla("".join(out))
        return bool(out)

    def _view_blocks(self, scene, camera, width, height):
        out = []
        text = camera.to_rdla()
        if self._changed("#camera", text):
            out.append(text)
        text = self._scene_variables(scene, camera, width, height)
        if self._changed("#scenevars", text):
            out.append(text)
        return out

    def _scene_variables(self, scene, camera, width, height):
        mr = scene.moonray
        samples = mr.viewport_pixel_samples if self.viewport else mr.pixel_samples
        attrs = {
            "image_width": rdla.i(width),
            "image_height": rdla.i(height),
            "camera": rdla.ref(camera.rdl_class, camera.rdl_name),
            "layer": rdla.ref("Layer", LAYER),
            "pixel_samples": rdla.i(samples),
            "light_samples": rdla.i(mr.light_samples),
            "bsdf_samples": rdla.i(mr.bsdf_samples),
            "max_depth": rdla.i(mr.max_depth),
            "max_diffuse_depth": rdla.i(mr.max_diffuse_depth),
            "max_glossy_depth": rdla.i(mr.max_glossy_depth),
            "max_mirror_depth": rdla.i(mr.max_mirror_depth),
            "sample_clamping_value": rdla.f(mr.sample_clamping_value),
            "pixel_filter": mr.pixel_filter,
            "frame": rdla.f(scene.frame_current),
            # MoonRay assumes centimeters (0.01); Blender works in meters
            "scene_scale": rdla.f(scene.unit_settings.scale_length),
        }
        return "SceneVariables {\n" + "".join(
            f"    [{rdla.s(k)}] = {v},\n" for k, v in attrs.items()
        ) + "}\n"

    @staticmethod
    def _layout_rdla(geometries, lights):
        lightset = rdla.ref("LightSet", LIGHT_SET)
        lines = []
        for cls, name, parts in geometries:
            geo = rdla.ref(cls, name)
            for part, material in parts:
                lines.append(
                    f"    {{{geo}, {rdla.s(part)}, {rdla.ref('DwaBaseMaterial', material)}, {lightset}}},\n"
                )
        geo_refs = "".join(f"    {rdla.ref(cls, name)},\n" for cls, name, _ in geometries)
        light_refs = "".join(f"    {rdla.ref(cls, name)},\n" for name, cls in sorted(lights.items()))
        return (
            f"{rdla.ref('LightSet', LIGHT_SET)} {{\n{light_refs}}}\n"
            f"{rdla.ref('GeometrySet', GEOMETRY_SET)} {{\n{geo_refs}}}\n"
            f"{rdla.ref('Layer', LAYER)} {{\n{''.join(lines)}}}\n"
        )


class _InstanceView:
    """Wraps an evaluated object to use an instance's matrix."""

    def __init__(self, obj, matrix_world):
        self._obj = obj
        self.matrix_world = matrix_world

    def __getattr__(self, name):
        return getattr(self._obj, name)
