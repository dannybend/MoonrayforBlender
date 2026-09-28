# SPDX-License-Identifier: GPL-3.0-or-later

import bpy

ENGINE = "MOONRAY"

# Built-in Blender panels that make sense with MoonRay (lights, materials,
# world...). MOONRAY is added to their COMPAT_ENGINES on register.
_EXTRA_PANELS = (
    "EEVEE_MATERIAL_PT_context_material",
    "EEVEE_MATERIAL_PT_surface",
    "EEVEE_WORLD_PT_surface",
    "DATA_PT_EEVEE_light",
    "DATA_PT_light",
    "DATA_PT_lens",
    "DATA_PT_camera",
    "DATA_PT_camera_dof",
    "DATA_PT_camera_dof_aperture",
    "OBJECT_PT_visibility",
)

# Panels that don't apply even though they are tagged BLENDER_RENDER
_EXCLUDE = {
    "VIEWLAYER_PT_filter",
    "VIEWLAYER_PT_layer_passes",
}


def _compatible_panels():
    panels = []
    for name in _EXTRA_PANELS:
        panel = getattr(bpy.types, name, None)
        if panel is not None and hasattr(panel, "COMPAT_ENGINES"):
            panels.append(panel)
    for panel in bpy.types.Panel.__subclasses__():
        compat = getattr(panel, "COMPAT_ENGINES", None)
        if compat and "BLENDER_RENDER" in compat and panel.__name__ not in _EXCLUDE:
            panels.append(panel)
    return panels


class _MoonRayPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    COMPAT_ENGINES = {ENGINE}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


class MOONRAY_PT_sampling(_MoonRayPanel, bpy.types.Panel):
    bl_label = "Sampling"
    bl_context = "render"

    def draw(self, context):
        mr = context.scene.moonray
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(mr, "device")
        col = layout.column(align=True)
        col.prop(mr, "pixel_samples", text="Render")
        col.prop(mr, "viewport_pixel_samples", text="Viewport")
        col = layout.column(align=True)
        col.prop(mr, "light_samples")
        col.prop(mr, "bsdf_samples")
        layout.prop(mr, "sample_clamping_value")
        layout.prop(mr, "pixel_filter")


class MOONRAY_PT_light_paths(_MoonRayPanel, bpy.types.Panel):
    bl_label = "Light Paths"
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        mr = context.scene.moonray
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(mr, "max_depth")
        col.prop(mr, "max_diffuse_depth")
        col.prop(mr, "max_glossy_depth")
        col.prop(mr, "max_mirror_depth")


class MOONRAY_PT_viewport(_MoonRayPanel, bpy.types.Panel):
    bl_label = "Viewport"
    bl_context = "render"

    def draw(self, context):
        mr = context.scene.moonray
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(mr, "viewport_resolution")
        layout.prop(mr, "viewport_fps")


class MOONRAY_PT_system(_MoonRayPanel, bpy.types.Panel):
    bl_label = "System"
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(context.scene.moonray, "threads")
        row = layout.row()
        row.operator("moonray.start_bridge", icon='PLAY')
        row.operator("moonray.stop_bridge", icon='PAUSE')


class MOONRAY_PT_light(_MoonRayPanel, bpy.types.Panel):
    bl_label = "MoonRay"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return super().poll(context) and context.light is not None

    def draw(self, context):
        mr = context.light.moonray
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(mr, "intensity_scale")
        layout.prop(mr, "visible_in_camera")


classes = (
    MOONRAY_PT_sampling,
    MOONRAY_PT_light_paths,
    MOONRAY_PT_viewport,
    MOONRAY_PT_system,
    MOONRAY_PT_light,
)


def register():
    for panel in _compatible_panels():
        panel.COMPAT_ENGINES.add(ENGINE)


def unregister():
    for panel in _compatible_panels():
        panel.COMPAT_ENGINES.discard(ENGINE)
