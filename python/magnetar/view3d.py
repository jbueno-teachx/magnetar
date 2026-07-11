# SPDX-License-Identifier: CC0-1.0
"""3D view / camera: orientation matrix, orbit, and world→screen projection."""

import math
from typing import Sequence, Tuple

Vec2 = Tuple[float, float]
Vec3f = Tuple[float, float, float]
# Row-major 3×3: view_coords = R @ world_coords (about the look-at origin).
Mat3 = Tuple[Vec3f, Vec3f, Vec3f]

IDENTITY_MAT3: Mat3 = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


class ViewCamera:
    """Camera-relative orbit and perspective projection of world points.

    Bound to :class:`~magnetar.app.MagnetarApp` as ``app.view`` (not a mixin).
    """

    def __init__(
        self,
        *,
        camera_offset: Vec3f = (0.0, 0.0, 0.0),
        world_scale: float = 80.0,
        perspective: float = 0.08,
        viewport_size: Tuple[int, int] = (1024, 768),
    ) -> None:
        self.camera_offset: Vec3f = camera_offset
        self.view_matrix: Mat3 = IDENTITY_MAT3
        self.world_scale: float = float(world_scale)
        self.perspective: float = float(perspective)
        self.viewport_size: Tuple[int, int] = (
            int(viewport_size[0]),
            int(viewport_size[1]),
        )

    # -- Euler façade (HUD / API) ---------------------------------------------

    @property
    def world_rotation(self) -> Vec3f:
        """Euler (yaw, pitch, roll) extracted from :attr:`view_matrix`."""
        return self.matrix_to_yaw_pitch_roll(self.view_matrix)

    @world_rotation.setter
    def world_rotation(self, ypr: Sequence[float]) -> None:
        yaw, pitch, roll = float(ypr[0]), float(ypr[1]), float(ypr[2])
        self.view_matrix = self.euler_to_matrix(
            self.wrap_yaw(yaw), self.clamp_pitch(pitch), roll
        )

    def reset(self) -> None:
        """Identity orientation (look along default axes)."""
        self.view_matrix = IDENTITY_MAT3

    # -- linear algebra -------------------------------------------------------

    @staticmethod
    def mat_mul(a: Mat3, b: Mat3) -> Mat3:
        """Return ``a @ b`` for row-major 3×3 matrices."""
        rows: list[Vec3f] = []
        for i in range(3):
            rows.append(
                (
                    a[i][0] * b[0][0] + a[i][1] * b[1][0] + a[i][2] * b[2][0],
                    a[i][0] * b[0][1] + a[i][1] * b[1][1] + a[i][2] * b[2][1],
                    a[i][0] * b[0][2] + a[i][1] * b[1][2] + a[i][2] * b[2][2],
                )
            )
        return (rows[0], rows[1], rows[2])

    @staticmethod
    def mat_vec(m: Mat3, x: float, y: float, z: float) -> Vec3f:
        return (
            m[0][0] * x + m[0][1] * y + m[0][2] * z,
            m[1][0] * x + m[1][1] * y + m[1][2] * z,
            m[2][0] * x + m[2][1] * y + m[2][2] * z,
        )

    @staticmethod
    def rot_x(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))

    @staticmethod
    def rot_y(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))

    @staticmethod
    def rot_z(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))

    @classmethod
    def euler_to_matrix(cls, yaw: float, pitch: float, roll: float) -> Mat3:
        """Fixed-axis Euler rebuild: R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
        return cls.mat_mul(cls.rot_z(yaw), cls.mat_mul(cls.rot_y(pitch), cls.rot_x(roll)))

    @staticmethod
    def matrix_to_yaw_pitch_roll(m: Mat3) -> Vec3f:
        """Extract (yaw, pitch, roll); yaw wrapped to [0, 2π)."""
        sy = max(-1.0, min(1.0, -m[2][0]))
        pitch = math.asin(sy)
        if abs(sy) < 0.999999:
            yaw = math.atan2(m[1][0], m[0][0])
            roll = math.atan2(m[2][1], m[2][2])
        else:
            yaw = math.atan2(-m[0][1], m[1][1])
            roll = 0.0
        yaw = yaw % (2.0 * math.pi)
        return (yaw, pitch, roll)

    @staticmethod
    def wrap_yaw(yaw: float) -> float:
        return yaw % (2.0 * math.pi)

    @staticmethod
    def clamp_pitch(pitch: float, limit: float = math.pi / 2) -> float:
        return max(-limit, min(limit, pitch))

    # -- orbit / project ------------------------------------------------------

    def orbit_camera(self, d_yaw: float, d_pitch: float) -> None:
        """Compose a camera-relative orbit onto the current view matrix.

        ``d_yaw`` / ``d_pitch`` rotate about the *current* view up / right axes.
        Pitch is soft-limited to ±90°; yaw is free (HUD wraps to 0–360°).
        """
        if d_yaw == 0.0 and d_pitch == 0.0:
            return
        if d_yaw != 0.0:
            self.view_matrix = self.mat_mul(self.rot_y(d_yaw), self.view_matrix)
        if d_pitch != 0.0:
            trial = self.mat_mul(self.rot_x(d_pitch), self.view_matrix)
            _, pitch, _ = self.matrix_to_yaw_pitch_roll(trial)
            if abs(pitch) <= math.pi / 2 + 1e-9:
                self.view_matrix = trial
            else:
                _, cur_pitch, _ = self.matrix_to_yaw_pitch_roll(self.view_matrix)
                target = math.copysign(math.pi / 2, d_pitch)
                fix = target - cur_pitch
                if abs(fix) > 1e-9 and (fix * d_pitch) > 0:
                    self.view_matrix = self.mat_mul(self.rot_x(fix), self.view_matrix)

    def rotate_point(self, x: float, y: float, z: float) -> Vec3f:
        """Apply the current view matrix to a world-space point."""
        return self.mat_vec(self.view_matrix, x, y, z)

    def project(
        self,
        point: Sequence[float],
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> Tuple[Vec2, float]:
        """Project a 3D world point (meters) to screen coordinates ``(u, v)``.

        Returns ``((u, v), depth)`` with view-space z as depth (larger = farther).
        """
        if width is None:
            width = self.viewport_size[0]
        if height is None:
            height = self.viewport_size[1]

        ox, oy, oz = self.camera_offset
        x = float(point[0]) - ox
        y = float(point[1]) - oy
        z = float(point[2]) - oz

        x, y, z = self.rotate_point(x, y, z)

        factor = 1.0 / max(0.2, 1.0 + z * self.perspective)
        u = width * 0.5 + x * self.world_scale * factor
        v = height * 0.5 - y * self.world_scale * factor
        return (u, v), z
