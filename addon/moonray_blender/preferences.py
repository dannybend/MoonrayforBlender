# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from . import bridge_process


class MOONRAY_OT_start_bridge(bpy.types.Operator):
    bl_idname = "moonray.start_bridge"
    bl_label = "Start moonray_bridge"
    bl_description = "Start the moonray_bridge server inside WSL"

    def execute(self, context):
        try:
            bridge_process.ensure_running(get_prefs(context))
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, "moonray_bridge is running")
        return {'FINISHED'}


class MOONRAY_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "moonray.stop_bridge"
    bl_label = "Stop moonray_bridge"
    bl_description = "Stop the moonray_bridge server"

    def execute(self, context):
        bridge_process.stop(get_prefs(context))
        return {'FINISHED'}


class MoonRayPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    wsl_distro: StringProperty(
        name="WSL Distribution",
        description="WSL distribution where MoonRay is built",
        default="AlmaLinux-9",
    )
    wsl_user: StringProperty(
        name="WSL User",
        default="root",
    )
    bridge_script: StringProperty(
        name="Bridge Script",
        description="Path (inside WSL) of the script that starts moonray_bridge",
        default="/opt/MoonRay/bridge/run_bridge.sh",
    )
    host: StringProperty(name="Host", default="127.0.0.1")
    port: IntProperty(name="Port", default=5577, min=1024, max=65535)
    autostart: BoolProperty(
        name="Auto-start",
        description="Launch moonray_bridge in WSL when rendering if it isn't running",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        col = layout.column()
        col.prop(self, "wsl_distro")
        col.prop(self, "wsl_user")
        col.prop(self, "bridge_script")
        col.separator()
        col.prop(self, "host")
        col.prop(self, "port")
        col.prop(self, "autostart")
        row = layout.row()
        row.operator(MOONRAY_OT_start_bridge.bl_idname, icon='PLAY')
        row.operator(MOONRAY_OT_stop_bridge.bl_idname, icon='PAUSE')


class _DefaultPrefs:
    """Defaults used when the add-on is loaded without being enabled (tests)."""
    wsl_distro = "AlmaLinux-9"
    wsl_user = "root"
    bridge_script = "/opt/MoonRay/bridge/run_bridge.sh"
    host = "127.0.0.1"
    port = 5577
    autostart = True


def get_prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else _DefaultPrefs()


classes = (
    MOONRAY_OT_start_bridge,
    MOONRAY_OT_stop_bridge,
    MoonRayPreferences,
)
