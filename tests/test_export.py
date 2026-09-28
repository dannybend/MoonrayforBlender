# SPDX-License-Identifier: GPL-3.0-or-later
#
# Exporter test without MoonRay: registers the add-on, builds a scene and
# captures the messages that would be sent to the bridge.
#
# Usage:
#   blender --background --factory-startup --python tests/test_export.py

import os
import struct
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))

import moonray_blender  # noqa: E402
from moonray_blender import protocol as P  # noqa: E402
from moonray_blender.export import camera as cam_export  # noqa: E402
from moonray_blender.export.scene import SceneSync  # noqa: E402


class FakeClient:
    def __init__(self):
        self.messages = []

    def send(self, msg_type, payload=b""):
        self.messages.append((msg_type, bytes(payload)))

    def send_rdla(self, text):
        if text:
            self.send(P.RDLA, text.encode())

    def take(self):
        msgs, self.messages = self.messages, []
        return msgs


def summarize(msgs):
    for t, payload in msgs:
        if t == P.RDLA:
            print("---- RDLA ----")
            print(payload.decode())
        elif t == P.MESH:
            n = struct.unpack_from("<I", payload, 0)[0]
            name = payload[4:4 + n].decode()
            flags, nv, nf, ni, nuv, nn, np_ = struct.unpack_from("<7I", payload, 4 + n)
            print(f"---- MESH {name}: {nv} verts, {nf} faces, {ni} indices, {nuv} uvs, {nn} normals, {np_} parts")
        elif t == P.CLEAR:
            print("---- CLEAR", payload.decode())


def build_scene():
    scene = bpy.context.scene
    scene.render.engine = "MOONRAY"
    scene.render.resolution_x = 320
    scene.render.resolution_y = 240

    # Textured material to exercise ImageMap
    mat = bpy.data.materials.new("Rojo")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    img = bpy.data.images.new("tex", 4, 4)
    img.filepath_raw = "C:\\texturas\\madera.png"
    img.source = 'FILE'
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bpy.data.objects["Cube"].data.materials[0] = mat

    # Floor and collection instances
    bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, -1))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(3, 0, 0))
    sphere = bpy.context.object
    bpy.ops.object.shade_smooth()

    coll = bpy.data.collections.new("Instanciable")
    coll.objects.link(sphere)
    bpy.ops.object.collection_instance_add(collection=coll.name, location=(0, 3, 0))

    # Sun + area light
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 5))
    bpy.ops.object.light_add(type='AREA', location=(0, -3, 3))
    bpy.context.object.data.shape = 'RECTANGLE'
    bpy.context.object.data.size_y = 2.0
    return scene


def main():
    moonray_blender.register()
    scene = build_scene()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    client = FakeClient()
    sync = SceneSync(client, viewport=False)
    w, h = 320, 240
    camera = cam_export.from_scene_camera(depsgraph, scene.camera, w, h)

    print("========== INITIAL SYNC ==========")
    changed = sync.sync(depsgraph, camera, w, h)
    summarize(client.take())
    assert changed

    print("========== NO CHANGES ==========")
    changed = sync.sync(depsgraph, camera, w, h, dirty_geometry=set())
    msgs = client.take()
    summarize(msgs)
    assert not changed and not msgs, "a sync without changes must not send anything"

    print("========== MOVE CUBE ==========")
    bpy.data.objects["Cube"].location.x += 1.0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    changed = sync.sync(depsgraph, camera, w, h, dirty_geometry=set())
    msgs = client.take()
    summarize(msgs)
    assert changed and all(t == P.RDLA for t, _ in msgs), "moving must only send RDLA, not meshes"

    print("========== DELETE LIGHT ==========")
    bpy.data.objects.remove(bpy.data.objects["Sun"])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    changed = sync.sync(depsgraph, camera, w, h, dirty_geometry=set())
    summarize(client.take())
    assert changed

    print("OK: exporter works")


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
