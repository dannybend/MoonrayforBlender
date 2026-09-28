# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty


class MoonRaySceneSettings(bpy.types.PropertyGroup):
    # -- Sampling ----------------------------------------------------------
    pixel_samples: IntProperty(
        name="Pixel Samples",
        description="Square root of the primary samples per pixel (8 = 64 samples)",
        default=8, min=1, soft_max=32,
    )
    viewport_pixel_samples: IntProperty(
        name="Viewport Samples",
        description="Square root of the samples per pixel in the viewport",
        default=4, min=1, soft_max=16,
    )
    light_samples: IntProperty(name="Light Samples", default=2, min=1, soft_max=16)
    bsdf_samples: IntProperty(name="BSDF Samples", default=2, min=1, soft_max=16)

    # -- Light paths -------------------------------------------------------
    max_depth: IntProperty(name="Total", default=5, min=0, soft_max=32)
    max_diffuse_depth: IntProperty(name="Diffuse", default=2, min=0, soft_max=32)
    max_glossy_depth: IntProperty(name="Glossy", default=2, min=0, soft_max=32)
    max_mirror_depth: IntProperty(name="Mirror", default=3, min=0, soft_max=32)

    # -- Image -------------------------------------------------------------
    sample_clamping_value: FloatProperty(
        name="Clamp Samples",
        description="Clamp indirect sample values to reduce fireflies (0 = disabled)",
        default=10.0, min=0.0,
    )
    pixel_filter: EnumProperty(
        name="Pixel Filter",
        items=[
            ('0', "Box", ""),
            ('1', "Cubic B-Spline", ""),
            ('2', "Quadratic B-Spline", ""),
        ],
        default='1',
    )

    # -- Viewport ----------------------------------------------------------
    viewport_resolution: EnumProperty(
        name="Viewport Resolution",
        description="Divide the viewport resolution for faster feedback",
        items=[
            ('1', "1:1", ""),
            ('2', "1:2", ""),
            ('4', "1:4", ""),
            ('8', "1:8", ""),
        ],
        default='2',
    )
    viewport_fps: FloatProperty(
        name="Refresh Rate",
        description="Maximum frames per second MoonRay sends to the viewport",
        default=20.0, min=1.0, max=60.0,
    )

    # -- System ------------------------------------------------------------
    device: EnumProperty(
        name="Device",
        description="Where MoonRay renders",
        items=[
            ('CPU', "CPU", "Vectorized CPU rendering (MoonRay's main mode)"),
            ('GPU', "GPU (CUDA/OptiX)",
             "MoonRay XPU mode: uses the NVIDIA GPU and falls back to CPU when the "
             "scene uses unsupported features. Requires MoonRay built with OptiX"),
        ],
        default='CPU',
    )
    threads: IntProperty(
        name="Threads",
        description="Render threads (0 = automatic)",
        default=0, min=0, max=256,
    )


class MoonRayLightSettings(bpy.types.PropertyGroup):
    intensity_scale: FloatProperty(
        name="Intensity Multiplier",
        description="Extra intensity multiplier on top of the automatic conversion from Blender units",
        default=1.0, min=0.0, soft_max=100.0,
    )
    visible_in_camera: BoolProperty(name="Visible in Camera", default=False)


classes = (
    MoonRaySceneSettings,
    MoonRayLightSettings,
)


def register():
    bpy.types.Scene.moonray = PointerProperty(type=MoonRaySceneSettings)
    bpy.types.Light.moonray = PointerProperty(type=MoonRayLightSettings)


def unregister():
    del bpy.types.Light.moonray
    del bpy.types.Scene.moonray
