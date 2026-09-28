# SPDX-License-Identifier: GPL-3.0-or-later
#
# Blender lights -> MoonRay lights.
#
# Unit conversion. With "normalized" = true and "apply_scene_scale" = false,
# MoonRay uses radiance = intensity / area, so the total power (lambertian
# emitter) is intensity * pi regardless of size:
#   - Point / Area (W):   intensity = W / pi       (same total power)
#   - Spot (W):           intensity = W / (4 pi)   (same on-axis intensity)
#   - Sun (W/m2):         intensity = E / pi       (normalized DistantLight: a
#                         white diffuse surface returns radiance = intensity)
# apply_scene_scale = true (the default) assumes centimeters and multiplies the
# radiance by 1/(scene_scale² * pi), so it is disabled.
# Verified against Cycles with single-light test scenes; the per-light
# multiplier allows fine tuning.

import math

from mathutils import Matrix

from . import rdla

# As in Blender, MoonRay lights emit towards local -Z: the object matrix is
# used as is (verified against Cycles).

WORLD_LIGHT = "/blender/world"


def light_name(obj_name):
    return "/blender/light/" + rdla.safe_name(obj_name)


def _normalized(matrix):
    loc, rot, _scale = matrix.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def light_rdla(name, obj):
    """Returns (class, RDLA text) for the light, or (None, None) if unsupported."""
    light = obj.data
    mr = light.moonray
    xform = _normalized(obj.matrix_world)
    scale = obj.matrix_world.to_scale()

    attrs = {
        "on": "true",
        "color": rdla.rgb(light.color),
        "visible_in_camera": "1" if mr.visible_in_camera else "0",
        "normalized": "true",
    }
    if light.type != 'SUN':
        attrs["apply_scene_scale"] = "false"

    if light.type == 'POINT':
        cls = "SphereLight"
        attrs["radius"] = rdla.f(max(light.shadow_soft_size, 1e-4))
        intensity = light.energy / math.pi
    elif light.type == 'SPOT':
        cls = "SpotLight"
        outer = math.degrees(light.spot_size)
        attrs["outer_cone_angle"] = rdla.f(outer)
        attrs["inner_cone_angle"] = rdla.f(outer * (1.0 - light.spot_blend))
        attrs["lens_radius"] = rdla.f(max(light.shadow_soft_size, 1e-4))
        intensity = light.energy / (4.0 * math.pi)
    elif light.type == 'SUN':
        cls = "DistantLight"
        attrs["angular_extent"] = rdla.f(max(math.degrees(light.angle), 1e-3))
        intensity = light.energy / math.pi
    elif light.type == 'AREA':
        if light.shape in {'DISK', 'ELLIPSE'}:
            cls = "DiskLight"
            attrs["radius"] = rdla.f(light.size * 0.5 * max(scale.x, scale.y))
        else:
            cls = "RectLight"
            size_y = light.size if light.shape == 'SQUARE' else light.size_y
            attrs["width"] = rdla.f(light.size * scale.x)
            attrs["height"] = rdla.f(size_y * scale.y)
        attrs["spread"] = rdla.f(min(max(light.spread / math.pi, 0.0), 1.0))
        intensity = light.energy / math.pi
    else:
        return None, None

    attrs["intensity"] = rdla.f(intensity * mr.intensity_scale)
    attrs["node_xform"] = rdla.mat4(xform)
    return cls, rdla.block(cls, name, attrs)


def light_off_rdla(cls, name):
    return rdla.block(cls, name, {"on": "false"})


# -- World ---------------------------------------------------------------

# MoonRay's EnvLight uses +Y as "up"; Blender uses +Z
_ENV_XFORM = Matrix.Rotation(math.pi / 2.0, 4, 'X')


def world_rdla(world, texture_path_fn):
    """EnvLight from the world's Background node. None if there is no world."""
    if world is None:
        return None

    color = (0.0, 0.0, 0.0)
    strength = 0.0
    texture = None

    if getattr(world, "use_nodes", True) and world.node_tree:
        output = _active_output(world.node_tree, 'ShaderNodeOutputWorld')
        bg = None
        if output and output.inputs["Surface"].is_linked:
            bg = output.inputs["Surface"].links[0].from_node
        if bg is not None and bg.bl_idname == 'ShaderNodeBackground':
            color_in = bg.inputs["Color"]
            strength = bg.inputs["Strength"].default_value
            color = tuple(color_in.default_value[:3])
            if color_in.is_linked:
                src = color_in.links[0].from_node
                if src.bl_idname == 'ShaderNodeTexEnvironment' and src.image is not None:
                    texture = texture_path_fn(src.image)
                    color = (1.0, 1.0, 1.0)
    else:
        color = tuple(world.color)
        strength = 1.0

    attrs = {
        "on": "true" if strength > 0.0 else "false",
        "color": rdla.rgb(color),
        "intensity": rdla.f(strength),
        "visible_in_camera": "1",
        "node_xform": rdla.mat4(_ENV_XFORM),
        "texture": rdla.s(texture or ""),
    }
    return rdla.block("EnvLight", WORLD_LIGHT, attrs)


def _active_output(tree, idname):
    outputs = [n for n in tree.nodes if n.bl_idname == idname]
    for n in outputs:
        if n.is_active_output:
            return n
    return outputs[0] if outputs else None
