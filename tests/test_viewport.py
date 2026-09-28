# SPDX-License-Identifier: GPL-3.0-or-later
#
# Interactive viewport rendering test (needs a GUI).
#
# Usage:
#   blender --factory-startup --python tests/test_viewport.py
#
# Switches the viewport to Rendered mode with MoonRay, waits for it to
# converge, orbits the view and moves the cube (to exercise incremental
# updates), saves screenshots to tests/out/ and quits Blender.

import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(HERE, "..", "addon"))

import moonray_blender  # noqa: E402

os.makedirs(OUT, exist_ok=True)
moonray_blender.register()

scene = bpy.context.scene
scene.render.engine = "MOONRAY"
scene.moonray.viewport_pixel_samples = 3


def view3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return window, area
    return None, None


def screenshot(name):
    window, area = view3d()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.screen.screenshot_area(filepath=os.path.join(OUT, name))
    print("[test_viewport] screenshot:", name)


steps = []


def step(delay):
    def deco(fn):
        steps.append((delay, fn))
        return fn
    return deco


@step(2.0)
def start():
    window, area = view3d()
    area.spaces.active.shading.type = 'RENDERED'
    area.spaces.active.overlay.show_overlays = False


@step(12.0)
def first():
    screenshot("viewport_1_initial.png")
    # Orbit the view by 40 degrees
    window, area = view3d()
    rv3d = area.spaces.active.region_3d
    from mathutils import Quaternion
    rv3d.view_rotation = Quaternion((0, 0, 1), 0.7) @ rv3d.view_rotation


@step(8.0)
def orbit():
    screenshot("viewport_2_orbited.png")
    cube = bpy.data.objects["Cube"]
    cube.location.z += 1.0
    cube.rotation_euler.z = 0.6
    bpy.data.materials["Material"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.3, 0.9, 1)


@step(8.0)
def moved():
    screenshot("viewport_3_cube_moved.png")


@step(1.0)
def quit_blender():
    print("[test_viewport] done")
    bpy.ops.wm.quit_blender()


def run_next():
    if not steps:
        return None
    _, fn = steps.pop(0)
    try:
        fn()
    except Exception:
        import traceback
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None
    return steps[0][0] if steps else None


bpy.app.timers.register(run_next, first_interval=steps[0][0])
