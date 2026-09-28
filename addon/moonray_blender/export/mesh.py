# SPDX-License-Identifier: GPL-3.0-or-later
#
# Conversion of Blender meshes to the bridge's binary MESH message.

import struct

import numpy as np


def _pack_str(text):
    data = text.encode("utf-8")
    return struct.pack("<I", len(data)) + data


def mesh_payload(name, mesh):
    """Serializes an evaluated mesh (bpy.types.Mesh).

    Returns (payload, parts), with parts = [(part_name, material_index)].
    Each distinct material index used by the mesh becomes a MoonRay "part", so
    the Layer can assign one material per part. If only one material is used,
    parts = [("", index)].
    """
    nverts = len(mesh.vertices)
    nfaces = len(mesh.polygons)
    nloops = len(mesh.loops)

    verts = np.empty(nverts * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", verts)

    counts = np.empty(nfaces, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", counts)

    indices = np.empty(nloops, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", indices)

    # Per-corner (face-varying) UVs: MoonRay infers the "rate" from the size
    uv_layer = mesh.uv_layers.active
    if uv_layer is not None and nloops:
        uvs = np.empty(nloops * 2, dtype=np.float32)
        uv_layer.uv.foreach_get("vector", uvs)
    else:
        uvs = np.empty(0, dtype=np.float32)

    # Per-corner normals cover smooth/flat shading, "auto smooth" and custom
    # normals in one go.
    if nloops:
        normals = np.empty(nloops * 3, dtype=np.float32)
        mesh.corner_normals.foreach_get("vector", normals)
    else:
        normals = np.empty(0, dtype=np.float32)

    # Parts by material index
    parts = [("", 0)]
    part_names = []
    part_counts = np.empty(0, dtype=np.int32)
    part_indices = np.empty(0, dtype=np.int32)
    if nfaces and len(mesh.materials) > 1:
        mat_idx = np.empty(nfaces, dtype=np.int32)
        mesh.polygons.foreach_get("material_index", mat_idx)
        used = np.unique(mat_idx)
        if len(used) > 1:
            part_indices = np.argsort(mat_idx, kind="stable").astype(np.int32)
            part_counts = np.array([np.count_nonzero(mat_idx == m) for m in used], dtype=np.int32)
            part_names = [f"slot{m}" for m in used]
            parts = [(f"slot{m}", int(m)) for m in used]
        else:
            parts = [("", int(used[0]))]

    header = _pack_str(name) + struct.pack(
        "<7I",
        0,  # flags
        nverts, nfaces, nloops,
        len(uvs) // 2, len(normals) // 3,
        len(part_names),
    )
    payload = b"".join((
        header,
        verts.tobytes(),
        counts.tobytes(),
        indices.tobytes(),
        uvs.tobytes(),
        normals.tobytes(),
        b"".join(_pack_str(p) for p in part_names),
        part_counts.tobytes(),
        part_indices.tobytes(),
    ))
    return payload, parts
