# SPDX-License-Identifier: GPL-3.0-or-later
#
# Real final render (F12) with MoonRay through the bridge.
#
# Usage:
#   blender --background --factory-startup --python tests/test_render.py -- [out.png] [MOONRAY|CYCLES] [CPU|GPU]
#
# Starts moonray_bridge in WSL if it isn't running.

import os
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))

import moonray_blender  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else os.path.join(HERE, "out", "render.png")
    engine = argv[1] if len(argv) > 1 else "MOONRAY"  # CYCLES to compare
    device = argv[2] if len(argv) > 2 else "CPU"
    os.makedirs(os.path.dirname(out), exist_ok=True)

    moonray_blender.register()
    scene = bpy.context.scene
    scene.render.engine = engine
    if engine == "CYCLES":
        scene.cycles.samples = 64
    scene.render.resolution_x = 480
    scene.render.resolution_y = 270
    scene.render.resolution_percentage = 100
    scene.moonray.pixel_samples = 3
    scene.moonray.device = device

    # Red cube, grey floor, a sphere and a big area light
    mat = bpy.data.materials["Material"]
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.05, 0.05, 1)
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -1))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.7, location=(2.2, 0.5, -0.3))
    bpy.ops.object.shade_smooth()
    bpy.ops.object.light_add(type='AREA', location=(-2, -2, 4))
    area = bpy.context.object
    area.data.energy = 800
    area.data.size = 2
    area.rotation_euler = (0.5, -0.4, 0)

    t = time.monotonic()
    bpy.ops.render.render(write_still=False)
    print(f"Rendered in {time.monotonic() - t:.1f} s")

    scene.render.image_settings.color_mode = 'RGB'
    bpy.data.images["Render Result"].save_render(out)
    print("Saved:", out)

    loaded = bpy.data.images.load(out)
    px = np.array(loaded.pixels[:], dtype=np.float32).reshape(loaded.size[1], loaded.size[0], 4)
    print("mean RGB:", px[..., :3].mean())


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(1)
