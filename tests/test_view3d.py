# SPDX-License-Identifier: CC0-1.0
import math

from magnetar.units import meters
from magnetar.view3d import IDENTITY_MAT3, ViewCamera


def test_project_origin_center() -> None:
    cam = ViewCamera(viewport_size=(200, 100))
    (u, v), depth = cam.project(meters(0, 0, 0))
    assert u == 100.0
    assert v == 50.0
    assert depth == 0.0


def test_orbit_changes_matrix_and_reset() -> None:
    cam = ViewCamera()
    assert cam.view_matrix == IDENTITY_MAT3
    cam.orbit_camera(math.radians(15), 0.0)
    assert cam.view_matrix != IDENTITY_MAT3
    cam.reset()
    assert cam.view_matrix == IDENTITY_MAT3


def test_yaw_wrap_in_euler_facade() -> None:
    cam = ViewCamera()
    cam.world_rotation = (-0.1, 0.0, 0.0)
    yaw, pitch, roll = cam.world_rotation
    assert 0.0 <= yaw < 2 * math.pi
    assert pitch == 0.0
