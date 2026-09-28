# SPDX-License-Identifier: GPL-3.0-or-later
#
# Blender materials -> MoonRay DwaBaseMaterial.
#
# The shader connected to the material output is translated (Principled BSDF
# and a few basic BSDFs). Inputs linked directly to an Image Texture node
# become an ImageMap; any other link is ignored and the socket's default value
# is used.

from . import rdla

DEFAULT_MATERIAL = "/blender/material/__default__"


def material_name(mat):
    return "/blender/material/" + rdla.safe_name(mat.name)


def default_material_rdla():
    return rdla.block("DwaBaseMaterial", DEFAULT_MATERIAL, {
        "albedo": rdla.rgb((0.8, 0.8, 0.8)),
        "roughness": rdla.f(0.5),
    })


class _Builder:
    def __init__(self, mat_name, texture_path_fn):
        self.mat_name = mat_name
        self.texture_path_fn = texture_path_fn
        self.maps = []   # RDLA blocks of the maps, in order
        self.map_names = set()
        self.attrs = {}

    # -- socket helpers -----------------------------------------------------

    @staticmethod
    def _source(socket):
        """Node and output socket linked to `socket`, skipping reroutes."""
        if not socket.is_linked:
            return None, None
        link = socket.links[0]
        node, out = link.from_node, link.from_socket
        while node.bl_idname == 'NodeReroute':
            if not node.inputs[0].is_linked:
                return None, None
            link = node.inputs[0].links[0]
            node, out = link.from_node, link.from_socket
        return node, out

    def _image_map(self, node, out_socket, is_color):
        if node.image is None:
            return None
        path = self.texture_path_fn(node.image)
        if not path:
            return None
        name = f"{self.mat_name}/{rdla.safe_name(node.name)}"
        if out_socket is not None and out_socket.name == "Alpha":
            name += "/alpha"
        if name in self.map_names:
            return rdla.ref("ImageMap", name)
        self.map_names.add(name)
        colorspace = node.image.colorspace_settings.name
        srgb = is_color and colorspace not in {"Non-Color", "Linear Rec.709", "Linear", "Raw"}
        attrs = {
            "texture": rdla.s(path),
            "gamma": "1" if srgb else "0",
            "wrap_around": "true" if node.extension in {'REPEAT', 'MIRROR'} else "false",
        }
        if out_socket is not None and out_socket.name == "Alpha":
            attrs["alpha_only"] = "true"
        self.maps.append(rdla.block("ImageMap", name, attrs))
        return rdla.ref("ImageMap", name)

    def color(self, attr, socket, scale=1.0):
        value = socket.default_value
        self.attrs[attr] = rdla.rgb([c * scale for c in value[:3]])
        node, out = self._source(socket)
        if node is not None and node.bl_idname == 'ShaderNodeTexImage':
            m = self._image_map(node, out, is_color=True)
            if m:
                self.attrs[attr] = rdla.bind(m)

    def scalar(self, attr, socket, fn=None):
        value = socket.default_value
        self.attrs[attr] = rdla.f(fn(value) if fn else value)
        node, out = self._source(socket)
        if node is not None and node.bl_idname == 'ShaderNodeTexImage':
            m = self._image_map(node, out, is_color=False)
            if m:
                self.attrs[attr] = rdla.bind(m)

    def normal(self, socket):
        node, _ = self._source(socket)
        if node is None or node.bl_idname != 'ShaderNodeNormalMap':
            return
        tex, _ = self._source(node.inputs["Color"])
        if tex is None or tex.bl_idname != 'ShaderNodeTexImage' or tex.image is None:
            return
        path = self.texture_path_fn(tex.image)
        if not path:
            return
        name = f"{self.mat_name}/{rdla.safe_name(tex.name)}/normal"
        self.maps.append(rdla.block("ImageNormalMap", name, {
            "tangent_space_normal_texture": rdla.s(path),
            "normal_encoding": "0",
        }))
        self.attrs["input_normal"] = rdla.ref("ImageNormalMap", name)
        self.attrs["input_normal_dial"] = rdla.f(node.inputs["Strength"].default_value)

    # -- shaders ------------------------------------------------------------

    def principled(self, node):
        inp = node.inputs
        self.color("albedo", inp["Base Color"])
        self.scalar("roughness", inp["Roughness"])
        self.scalar("metallic", inp["Metallic"])
        self.color("metallic_color", inp["Base Color"])
        self.attrs["refractive_index"] = rdla.f(inp["IOR"].default_value)
        self.scalar("specular", inp["Specular IOR Level"], lambda v: min(2.0 * v, 2.0))
        self.scalar("presence", inp["Alpha"])

        transmission = inp["Transmission Weight"]
        self.scalar("transmission", transmission)
        self.color("transmission_color", inp["Base Color"])

        coat = inp["Coat Weight"].default_value
        if coat > 0.0 or inp["Coat Weight"].is_linked:
            self.attrs["show_clearcoat"] = "true"
            self.scalar("clearcoat", inp["Coat Weight"])
            self.scalar("clearcoat_roughness", inp["Coat Roughness"])
            self.attrs["clearcoat_refractive_index"] = rdla.f(inp["Coat IOR"].default_value)

        strength = inp["Emission Strength"].default_value
        if strength > 0.0:
            self.attrs["show_emission"] = "true"
            self.color("emission", inp["Emission Color"], scale=strength)

        self.normal(inp["Normal"])

    def diffuse(self, node):
        self.color("albedo", node.inputs["Color"])
        self.attrs["show_specular"] = "false"
        self.attrs["roughness"] = rdla.f(1.0)

    def glossy(self, node):
        self.attrs["metallic"] = rdla.f(1.0)
        self.color("metallic_color", node.inputs["Color"])
        self.scalar("roughness", node.inputs["Roughness"])
        self.normal(node.inputs["Normal"])

    def glass(self, node):
        self.attrs["transmission"] = rdla.f(1.0)
        self.color("transmission_color", node.inputs["Color"])
        self.scalar("roughness", node.inputs["Roughness"])
        self.attrs["refractive_index"] = rdla.f(node.inputs["IOR"].default_value)
        self.normal(node.inputs["Normal"])

    def emission(self, node):
        strength = node.inputs["Strength"].default_value
        self.attrs["show_diffuse"] = "false"
        self.attrs["show_specular"] = "false"
        self.attrs["show_emission"] = "true"
        self.color("emission", node.inputs["Color"], scale=strength)

    def fallback(self, mat):
        self.attrs["albedo"] = rdla.rgb(mat.diffuse_color)
        self.attrs["roughness"] = rdla.f(mat.roughness)
        self.attrs["metallic"] = rdla.f(mat.metallic)


_SHADERS = {
    'ShaderNodeBsdfPrincipled': _Builder.principled,
    'ShaderNodeBsdfDiffuse': _Builder.diffuse,
    'ShaderNodeBsdfGlossy': _Builder.glossy,
    'ShaderNodeBsdfAnisotropic': _Builder.glossy,
    'ShaderNodeBsdfGlass': _Builder.glass,
    'ShaderNodeEmission': _Builder.emission,
}


def _surface_node(mat):
    # use_nodes is deprecated in Blender 5 (always True)
    if not getattr(mat, "use_nodes", True) or mat.node_tree is None:
        return None
    outputs = [n for n in mat.node_tree.nodes if n.bl_idname == 'ShaderNodeOutputMaterial']
    output = next((n for n in outputs if n.is_active_output), outputs[0] if outputs else None)
    if output is None:
        return None
    node, _ = _Builder._source(output.inputs["Surface"])
    return node


def material_rdla(mat, texture_path_fn):
    """RDLA text with the material's maps and its DwaBaseMaterial."""
    name = material_name(mat)
    builder = _Builder(name, texture_path_fn)
    node = _surface_node(mat)
    handler = _SHADERS.get(node.bl_idname) if node is not None else None
    if handler is not None:
        handler(builder, node)
    else:
        builder.fallback(mat)
    return "".join(builder.maps) + rdla.block("DwaBaseMaterial", name, builder.attrs)
