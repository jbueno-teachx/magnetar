# SPDX-License-Identifier: CC0-1.0
"""Magnetar application: pygame 2D view of the 3D particle world.

View options are hardcoded here for now; camera and simulation controls
will grow around these defaults.
"""

import math
import os
import sys
from typing import Callable, Iterable, List, Sequence, Tuple

# Do not let SDL open a real audio device — pygame.init() would otherwise
# initialize the mixer and can pause / preempt other apps' playback.
# This is unrelated to OpenGL; it is the SDL audio subsystem.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.assets import DEFAULT_HUD_FONT_SIZE, hud_font_path
from magnetar.particles import ElectroParticle, Particle
from magnetar.prompt import InteractivePrompt
from magnetar.units import coulomb, gram, meters, second
from magnetar.widgets import DragImageButton, WidgetRegistry, make_curved_arrows_icon
from magnetar.world import World

# ---------------------------------------------------------------------------
# View options (hardcoded for the initial 2D projection of 3D space)
# ---------------------------------------------------------------------------

VIEW_WIDTH = 1024
VIEW_HEIGHT = 768
BACKGROUND_COLOR = (0, 0, 0)  # black
THEME_COLOR = (0, 255, 255)  # cyan

WINDOW_TITLE = "magnetar"
TARGET_FPS = 60

# Orthographic-ish scale: world meters → pixels (before perspective foreshortening).
WORLD_SCALE = 80.0
# Simple perspective: foreshortens view-space x/y by (1 + z * PERSPECTIVE).
PERSPECTIVE = 0.08
# Camera look-at origin offset in world space (meters).
CAMERA_OFFSET = (0.0, 0.0, 0.0)
# Initial view orientation (identity). Live orientation is a 3×3 matrix; orbit
# controls compose camera-relative increments on top of the *current* matrix.
WORLD_ROTATION = (0.0, 0.0, 0.0)  # legacy Euler seed (yaw, pitch, roll)

# Particle drawing
PARTICLE_RADIUS_PX = 8
ELECTRO_COLOR = THEME_COLOR
BOUND_COLOR = (255, 200, 64)  # fixed field sources
NEUTRAL_COLOR = (160, 160, 160)
AXIS_COLOR = (191, 191, 191)  # 75% gray — axes and axis labels
HUD_COLOR = THEME_COLOR

# Orbit control (bottom-right): click = 10°, drag = continuous rotate about origin.
ROTATE_CLICK_DEGREES = 10.0
ROTATE_DRAG_DEGREES_PER_PIXEL = 0.35
# Half the original control size; parked in the bottom-right corner.
ROTATE_WIDGET_W_PCT = 6.0
ROTATE_WIDGET_H_PCT = 8.0
ROTATE_WIDGET_X_PCT = 100.0 - ROTATE_WIDGET_W_PCT - 2.0  # 2% margin from right
ROTATE_WIDGET_Y_PCT = 100.0 - ROTATE_WIDGET_H_PCT - 2.0  # 2% margin from bottom


Vec2 = Tuple[float, float]
Vec3f = Tuple[float, float, float]
# Row-major 3×3: view_coords = R @ world_coords (about the look-at origin).
Mat3 = Tuple[Vec3f, Vec3f, Vec3f]
WorldFactory = Callable[[], World]

_IDENTITY_MAT3: Mat3 = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


def create_world() -> World:
    """Seed a small demo configuration so the window is not empty."""
    world = World()
    # Free charges (will later respond to E and B fields). Positions in meters.
    world.add_electro(
        meters(-2.0, 0.0, 0.0),
        charge=coulomb(1.0),
        mass=gram(1.0),
        label="E+",
    )
    world.add_electro(
        meters(2.0, 0.0, 0.0),
        charge=coulomb(-1.0),
        mass=gram(1.0),
        velocity=(-0.2, 0.1, 0.0),  # m/s
        label="E-",
    )
    # Bound charge: fixed in place, field source only.
    world.add_electro(
        meters(0.0, 1.5, 1.0),
        charge=coulomb(2.0),
        mass=gram(5.0),
        pinned=True,
        label="Efix",
    )
    return world


class MagnetarApp:
    """pygame front-end: owns the world, prompt, projection, and main loop."""

    def __init__(self, world_factory: WorldFactory = create_world) -> None:
        self.world_factory = world_factory
        self.world: World = world_factory()
        # World keeps the app via a per-instance ContextVar (Particle → World → App).
        self.world.bind_app(self)
        self.prompt = InteractivePrompt(self.world)

        # View / camera state (mutable; in-window controls will drive these).
        self.camera_offset: Vec3f = CAMERA_OFFSET
        # Orientation matrix (camera-relative orbit composes onto this).
        self.view_matrix: Mat3 = _IDENTITY_MAT3
        self.world_scale: float = WORLD_SCALE
        self.perspective: float = PERSPECTIVE
        self.particle_radius_px: int = PARTICLE_RADIUS_PX

        # pygame resources (filled in by start / _init_pygame)
        self.screen: pygame.Surface | None = None
        self.clock: pygame.time.Clock | None = None
        self.font: pygame.font.Font | None = None
        self.running: bool = False

        # In-window UI (registry filled after pygame init when surfaces exist).
        self.widgets = WidgetRegistry()
        self._orbit_button: DragImageButton | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> int:
        """Initialize pygame, run the loop, always shut down cleanly."""
        self._init_pygame()
        try:
            pygame.display.set_caption(WINDOW_TITLE)
            self.screen = pygame.display.set_mode((VIEW_WIDTH, VIEW_HEIGHT))
            self.clock = pygame.time.Clock()
            with hud_font_path() as font_file:
                self.font = pygame.font.Font(str(font_file), DEFAULT_HUD_FONT_SIZE)
            self._build_ui()
            self.prompt.start()
            return self.run()
        finally:
            self.prompt.stop()
            self._shutdown_pygame()

    def run(self) -> int:
        """Main loop only: tick → events → step → draw → flip."""
        assert self.screen is not None and self.clock is not None and self.font is not None
        self.running = True
        while True:
            dt = second(self.clock.tick(TARGET_FPS) / 1000.0)
            self.events()
            if not self.running:
                break
            self.world.step(dt)
            self.render_frame()
            pygame.display.flip()
        return 0

    def events(self) -> None:
        """Poll pygame events, widget registry, and the interactive prompt."""
        screen_size = (
            self.screen.get_size()
            if self.screen is not None
            else (VIEW_WIDTH, VIEW_HEIGHT)
        )
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE,
                pygame.K_q,
            ):
                self.running = False
                continue

            # Mouse → widget registry (mask gates work inside dispatch).
            if event.type in (
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
            ):
                if self.widgets.dispatch(event, screen_size):
                    continue

        if self.prompt.poll() is False:
            self.running = False

    # -- orientation / projection ---------------------------------------------

    @property
    def world_rotation(self) -> Vec3f:
        """Euler (yaw, pitch, roll) extracted from :attr:`view_matrix` for HUD/API."""
        return self._matrix_to_yaw_pitch_roll(self.view_matrix)

    @world_rotation.setter
    def world_rotation(self, ypr: Sequence[float]) -> None:
        """Set orientation from Euler angles (rebuilds :attr:`view_matrix`)."""
        yaw, pitch, roll = float(ypr[0]), float(ypr[1]), float(ypr[2])
        self.view_matrix = self._euler_to_matrix(
            self._wrap_yaw(yaw), self._clamp_pitch(pitch), roll
        )

    @staticmethod
    def _mat_mul(a: Mat3, b: Mat3) -> Mat3:
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
    def _mat_vec(m: Mat3, x: float, y: float, z: float) -> Vec3f:
        return (
            m[0][0] * x + m[0][1] * y + m[0][2] * z,
            m[1][0] * x + m[1][1] * y + m[1][2] * z,
            m[2][0] * x + m[2][1] * y + m[2][2] * z,
        )

    @staticmethod
    def _rot_x(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))

    @staticmethod
    def _rot_y(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))

    @staticmethod
    def _rot_z(angle: float) -> Mat3:
        c, s = math.cos(angle), math.sin(angle)
        return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))

    @classmethod
    def _euler_to_matrix(cls, yaw: float, pitch: float, roll: float) -> Mat3:
        """Fixed-axis Euler rebuild: R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
        return cls._mat_mul(cls._rot_z(yaw), cls._mat_mul(cls._rot_y(pitch), cls._rot_x(roll)))

    @staticmethod
    def _matrix_to_yaw_pitch_roll(m: Mat3) -> Vec3f:
        """Extract (yaw, pitch, roll) for display; yaw wrapped to [0, 2π)."""
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

    def _orbit_camera(self, d_yaw: float, d_pitch: float) -> None:
        """Compose a camera-relative orbit onto the current view matrix.

        ``d_yaw`` / ``d_pitch`` rotate about the *current* view up / right axes:
        ``R := Rx(d_pitch) @ Ry(d_yaw) @ R``. Each gesture starts from the live
        orientation (not fixed world axes). Camera keeps looking at the origin.

        Pitch is soft-limited to ±90° by rejecting the pitch part of a step that
        would push the extracted elevation outside that range; yaw is free
        (HUD shows it wrapped to 0–360°).
        """
        if d_yaw == 0.0 and d_pitch == 0.0:
            return
        # Apply yaw about current view-up first (left-multiply in view space).
        if d_yaw != 0.0:
            self.view_matrix = self._mat_mul(self._rot_y(d_yaw), self.view_matrix)
        if d_pitch != 0.0:
            trial = self._mat_mul(self._rot_x(d_pitch), self.view_matrix)
            _, pitch, _ = self._matrix_to_yaw_pitch_roll(trial)
            if abs(pitch) <= math.pi / 2 + 1e-9:
                self.view_matrix = trial
            else:
                # Nudge to the stop rather than overshooting past the pole.
                _, cur_pitch, _ = self._matrix_to_yaw_pitch_roll(self.view_matrix)
                target = math.copysign(math.pi / 2, d_pitch)
                fix = target - cur_pitch
                if abs(fix) > 1e-9 and (fix * d_pitch) > 0:
                    self.view_matrix = self._mat_mul(self._rot_x(fix), self.view_matrix)

    def _rotate_point(self, x: float, y: float, z: float) -> Vec3f:
        """Apply the current view matrix to a world-space point."""
        return self._mat_vec(self.view_matrix, x, y, z)

    def project(
        self,
        point: Sequence[float],
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> Tuple[Vec2, float]:
        """Project a 3D world point (meters) to screen coordinates ``(u, v)``.

        Pipeline: camera offset → view matrix → perspective → pixel space.
        Returns ``((u, v), depth)`` with view-space z as depth (larger = farther).
        """
        if width is None or height is None:
            if self.screen is not None:
                width = width if width is not None else self.screen.get_width()
                height = height if height is not None else self.screen.get_height()
            else:
                width = width if width is not None else VIEW_WIDTH
                height = height if height is not None else VIEW_HEIGHT

        ox, oy, oz = self.camera_offset
        x = float(point[0]) - ox
        y = float(point[1]) - oy
        z = float(point[2]) - oz

        x, y, z = self._rotate_point(x, y, z)

        factor = 1.0 / max(0.2, 1.0 + z * self.perspective)
        u = width * 0.5 + x * self.world_scale * factor
        v = height * 0.5 - y * self.world_scale * factor  # world +y → screen up
        return (u, v), z

    # -- drawing --------------------------------------------------------------

    def draw_axes(self) -> None:
        """Draw world axes through the same 3D → 2D pipeline as particles."""
        assert self.screen is not None
        surface = self.screen
        (u0, v0), _ = self.project(meters(0.0, 0.0, 0.0))
        ends = (
            ("X", *self.project(meters(3.0, 0.0, 0.0))[0]),
            ("Y", *self.project(meters(0.0, 3.0, 0.0))[0]),
            ("Z", *self.project(meters(0.0, 0.0, 3.0))[0]),
        )
        origin = (int(u0), int(v0))
        for name, ue, ve in ends:
            end = (int(ue), int(ve))
            pygame.draw.line(surface, AXIS_COLOR, origin, end, 2)
            # Label at 1/4 of the on-screen axis length from the origin.
            ul = u0 + 0.25 * (ue - u0)
            vl = v0 + 0.25 * (ve - v0)
            self._blit_axis_label(name, ul, vl)

    def _blit_axis_label(self, name: str, u: float, v: float) -> None:
        """Draw a 2D axis name near ``(u, v)``, shifted down so it sits below the axis."""
        assert self.screen is not None and self.font is not None
        text = self.font.render(name, True, AXIS_COLOR)
        # Screen +v is down; nudge by ~0.6× font height so labels sit under the line.
        down = int(round(0.6 * self.font.get_height()))
        self.screen.blit(
            text,
            (int(u) - text.get_width() // 2, int(v) - text.get_height() // 2 + down),
        )

    def draw_particle(self, particle: Particle, *, u: float, v: float) -> None:
        """Draw ``particle`` at projected screen coordinates ``(u, v)``."""
        assert self.screen is not None
        surface = self.screen
        u_i, v_i = int(u), int(v)
        r = PARTICLE_RADIUS_PX

        if particle.color is not None:
            color = particle.color
        elif particle.pinned:
            color = BOUND_COLOR
        elif isinstance(particle, ElectroParticle):
            color = ELECTRO_COLOR
        else:
            color = NEUTRAL_COLOR

        if isinstance(particle, ElectroParticle):
            width = 0 if particle.pinned else 2  # filled = fixed source
            pygame.draw.circle(surface, color, (u_i, v_i), r, width=width)
            mark = color if width else BACKGROUND_COLOR
            pygame.draw.line(surface, mark, (u_i - r // 2, v_i), (u_i + r // 2, v_i), 2)
            if particle.charge >= 0:
                pygame.draw.line(surface, mark, (u_i, v_i - r // 2), (u_i, v_i + r // 2), 2)
            if particle.pinned:
                pygame.draw.circle(surface, color, (u_i, v_i), r + 3, width=1)
        else:
            pygame.draw.circle(
                surface, color, (u_i, v_i), r // 2, width=0 if particle.pinned else 1
            )

    def draw_hud(self) -> None:
        assert self.screen is not None and self.font is not None
        yaw, pitch, roll = self.world_rotation
        lines = [
            f"magnetar  t={float(self.world.time):.2f}s  n={len(self.world)}",
            (
                f"view  yaw={math.degrees(yaw):.1f}°  "
                f"pitch={math.degrees(pitch):+.1f}°  "
                f"roll={math.degrees(roll):+.1f}°"
            ),
            "orbit: drag / click sides; center resets  |  Esc/q/Ctrl+D quit",
        ]
        y = 8
        for line in lines:
            text = self.font.render(line, True, HUD_COLOR)
            self.screen.blit(text, (10, y))
            y += text.get_height() + 2

    def render_frame(self) -> None:
        assert self.screen is not None
        self.screen.fill(BACKGROUND_COLOR)
        self.draw_axes()

        projected: List[Tuple[float, Particle, float, float]] = []
        for particle in self.world.particles:
            (u, v), depth = self.project(particle.position)
            projected.append((depth, particle, u, v))
        projected.sort(key=lambda item: item[0], reverse=True)
        for _, particle, u, v in projected:
            self.draw_particle(particle, u=u, v=v)

        self.draw_hud()
        self.widgets.draw(self.screen)

    # -- in-window UI ---------------------------------------------------------

    def _build_ui(self) -> None:
        """Create widgets once the display is available."""
        self.widgets.clear()
        icon = make_curved_arrows_icon(128, color=THEME_COLOR, accent=AXIS_COLOR)
        self._orbit_button = DragImageButton(
            ROTATE_WIDGET_X_PCT,
            ROTATE_WIDGET_Y_PCT,
            ROTATE_WIDGET_W_PCT,
            ROTATE_WIDGET_H_PCT,
            icon,
            name="orbit",
            command=self._on_orbit_click,
            on_drag=self._on_orbit_drag,
        )
        self.widgets.add(self._orbit_button)

    def _on_orbit_click(self, zone: str) -> None:
        """Discrete orbit step from the *current* orientation, or reset on center.

        Side zones apply ±10° about the current view axes (camera-relative).
        Center (Manhattan ≤ 10% of half-size) resets to identity.
        """
        if zone == "center":
            self.view_matrix = _IDENTITY_MAT3
            return
        step = math.radians(ROTATE_CLICK_DEGREES)
        if zone == "left":
            self._orbit_camera(-step, 0.0)
        elif zone == "right":
            self._orbit_camera(step, 0.0)
        elif zone == "up":
            self._orbit_camera(0.0, step)
        elif zone == "down":
            self._orbit_camera(0.0, -step)

    def _on_orbit_drag(self, dx: int, dy: int, total_dx: int, total_dy: int) -> None:
        """Continuous camera-relative orbit (drag may leave the widget)."""
        _ = (total_dx, total_dy)
        sens = math.radians(ROTATE_DRAG_DEGREES_PER_PIXEL)
        # Horizontal → yaw about current up; vertical → pitch about current right.
        self._orbit_camera(dx * sens, -dy * sens)

    @staticmethod
    def _wrap_yaw(yaw: float) -> float:
        """Keep yaw in [0, 2π) with wrap-around."""
        return yaw % (2.0 * math.pi)

    @staticmethod
    def _clamp_pitch(pitch: float, limit: float = math.pi / 2) -> float:
        """Keep pitch in [-90°, +90°] inclusive."""
        return max(-limit, min(limit, pitch))

    # -- pygame init / teardown -----------------------------------------------


    def _init_pygame(self) -> None:
        """Initialize only the subsystems we need — never the audio mixer."""
        pygame.display.init()
        pygame.font.init()
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()

    def _shutdown_pygame(self) -> None:
        pygame.quit()
        self.font = None
        self.screen = None
        self.clock = None


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point used by ``python -m magnetar`` and console scripts."""
    _ = list(argv) if argv is not None else sys.argv[1:]
    return MagnetarApp(world_factory=create_world).start()


if __name__ == "__main__":
    raise SystemExit(main())
