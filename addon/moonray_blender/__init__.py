# SPDX-License-Identifier: GPL-3.0-or-later
#
# MoonRay for Blender: a render engine that uses MoonRay (DreamWorks) through
# moonray_bridge, a server running inside WSL.

import bpy

from . import bridge_process, engine, preferences, properties, ui

_classes = (
    *preferences.classes,
    *properties.classes,
    *engine.classes,
    *ui.classes,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    properties.register()
    ui.register()


def unregister():
    ui.unregister()
    properties.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    bridge_process.stop()
