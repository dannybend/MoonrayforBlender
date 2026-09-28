# SPDX-License-Identifier: GPL-3.0-or-later
#
# Cameras: both the scene camera (F12) and the viewport view are converted from
# their projection matrix, so both paths share the same code and honor shift,
# sensor fit, view zoom, etc.

import math

from mathutils import Matrix

from . import rdla

PERSP_CAMERA = "/blender/camera/persp"
ORTHO_CAMERA = "/blender/camera/ortho"

# Arbitrary aperture in mm: only the focal/aperture ratio matters
_FILM_WIDTH = 36.0


class CameraParams:
    def __init__(self, cam_to_world, projection, ortho, near, far, dof=None):
        self.cam_to_world = cam_to_world
        self.projection = projection
        self.ortho = ortho
        self.near = near
        self.far = far
        self.dof = dof  # (focus distance, f-stop) or None

    @property
    def rdl_name(self):
        return ORTHO_CAMERA if self.ortho else PERSP_CAMERA

    @property
    def rdl_class(self):
        return "OrthographicCamera" if self.ortho else "PerspectiveCamera"

    def to_rdla(self):
        P = self.projection
        attrs = {
            "node_xform": rdla.mat4(self.cam_to_world),
            "near": rdla.f(self.near),
            "far": rdla.f(self.far),
        }
        if self.ortho:
            width = 2.0 / P[0][0]
            attrs["film_width_aperture"] = rdla.f(width)
            attrs["horizontal_film_offset"] = rdla.f(-P[0][3] / P[0][0])
            attrs["vertical_film_offset"] = rdla.f(-P[1][3] / P[0][0])
        else:
            attrs["film_width_aperture"] = rdla.f(_FILM_WIDTH)
            attrs["focal"] = rdla.f(_FILM_WIDTH * P[0][0] / 2.0)
            attrs["horizontal_film_offset"] = rdla.f(_FILM_WIDTH * P[0][2] / 2.0)
            attrs["vertical_film_offset"] = rdla.f(_FILM_WIDTH * P[1][2] / 2.0)
        if self.dof is not None:
            distance, fstop = self.dof
            attrs["dof"] = "true"
            attrs["dof_focus_distance"] = rdla.f(distance)
            attrs["dof_aperture"] = rdla.f(fstop)
        else:
            attrs["dof"] = "false"
        return rdla.block(self.rdl_class, self.rdl_name, attrs)

    def key(self):
        return self.to_rdla()


def _normalized(matrix):
    loc, rot, _scale = matrix.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def from_scene_camera(depsgraph, cam_obj, width, height):
    scene = depsgraph.scene
    render = scene.render
    cam = cam_obj.data
    projection = cam_obj.calc_matrix_camera(
        depsgraph, x=width, y=height,
        scale_x=render.pixel_aspect_x, scale_y=render.pixel_aspect_y,
    )
    ortho = cam.type == 'ORTHO'
    if cam.type == 'PANO':
        print("[MoonRay] Panoramic cameras are not supported yet; using perspective")

    dof = None
    if cam.dof.use_dof:
        if cam.dof.focus_object is not None:
            cam_pos = cam_obj.matrix_world.translation
            target = cam.dof.focus_object.matrix_world.translation
            distance = (target - cam_pos).length
        else:
            distance = cam.dof.focus_distance
        dof = (max(distance, 1e-4), cam.dof.aperture_fstop)

    return CameraParams(
        _normalized(cam_obj.matrix_world), projection, ortho,
        cam.clip_start, cam.clip_end, dof,
    )


def from_viewport(context):
    region_data = context.region_data
    space = context.space_data
    projection = region_data.window_matrix
    cam_to_world = region_data.view_matrix.inverted()
    ortho = not region_data.is_perspective

    if region_data.view_perspective == 'CAMERA' and space.camera is not None:
        cam = space.camera.data
        near, far = cam.clip_start, cam.clip_end
    else:
        near, far = space.clip_start, space.clip_end

    if ortho:
        # In ortho, Blender clips between -far/2 and +far/2 around the view:
        # move the camera back so what lies "behind" isn't lost.
        back = far * 0.5
        cam_to_world = cam_to_world @ Matrix.Translation((0.0, 0.0, back))
        near = 1e-3
    return CameraParams(_normalized(cam_to_world), projection.copy(), ortho, near, far)
