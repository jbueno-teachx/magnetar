# SPDX-License-Identifier: CC0-1.0
"""Magnetar application: pygame 2D view of the 3D particle world.

View options are hardcoded here for now; camera and simulation controls
will grow around these defaults.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Callable, Iterable, List, Sequence, Tuple

# Do not let SDL open a real audio device — pygame.init() would otherwise
# initialize the mixer and can pause / preempt other apps' playback.
# This is unrelated to OpenGL; it is the SDL audio subsystem.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.assets import DEFAULT_HUD_FONT_SIZE, hud_font_session
from magnetar.particles import ElectroParticle, Particle
from magnetar.prompt import InteractivePrompt
from magnetar.units import coulomb, gram, meters, second
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
# World rotation applied before projection: (yaw, pitch, roll) in radians about
# world Z, Y, X respectively. Identity (zeros) for now; camera/orbit will drive this.
WORLD_ROTATION = (0.0, 0.0, 0.0)

# Particle drawing
PARTICLE_RADIUS_PX = 8
ELECTRO_COLOR = THEME_COLOR
BOUND_COLOR = (255, 200, 64)  # fixed field sources
NEUTRAL_COLOR = (160, 160, 160)
AXIS_COLOR = (0, 80, 80)
HUD_COLOR = THEME_COLOR


Vec2 = Tuple[float, float]
Vec3f = Tuple[float, float, float]
WorldFactory = Callable[[], World]


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
        self.prompt = InteractivePrompt(self.world)

        # View / camera state (mutable; in-window controls will drive these).
        self.camera_offset: Vec3f = CAMERA_OFFSET
        self.world_rotation: Vec3f = WORLD_ROTATION
        self.world_scale: float = WORLD_SCALE
        self.perspective: float = PERSPECTIVE

        # pygame resources (filled in by start / _init_pygame)
        self.screen: pygame.Surface | None = None
        self.clock: pygame.time.Clock | None = None
        self.font: pygame.font.Font | None = None
        self._font_session = hud_font_session()
        self.running: bool = False

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> int:
        """Initialize pygame, run the loop, always shut down cleanly."""
        self._init_pygame()
        try:
            pygame.display.set_caption(WINDOW_TITLE)
            self.screen = pygame.display.set_mode((VIEW_WIDTH, VIEW_HEIGHT))
            self.clock = pygame.time.Clock()
            self.font = self._load_hud_font(DEFAULT_HUD_FONT_SIZE)
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
        """Poll pygame events and the interactive prompt; may clear ``running``."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE,
                pygame.K_q,
            ):
                self.running = False

        if self.prompt.poll() is False:
            self.running = False

    # -- projection -----------------------------------------------------------

    def _rotate_point(self, x: float, y: float, z: float) -> Vec3f:
        """Apply world rotation (yaw Z, pitch Y, roll X) to a view-space point."""
        yaw, pitch, roll = self.world_rotation
        if yaw == 0.0 and pitch == 0.0 and roll == 0.0:
            return (x, y, z)

        if roll != 0.0:
            cr, sr = math.cos(roll), math.sin(roll)
            y, z = y * cr - z * sr, y * sr + z * cr
        if pitch != 0.0:
            cp, sp = math.cos(pitch), math.sin(pitch)
            x, z = x * cp + z * sp, -x * sp + z * cp
        if yaw != 0.0:
            cy, sy = math.cos(yaw), math.sin(yaw)
            x, y = x * cy - y * sy, x * sy + y * cy
        return (x, y, z)

    def project(
        self,
        point: Sequence[float],
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> Tuple[Vec2, float]:
        """Project a 3D world point (meters) to screen coordinates ``(u, v)``.

        Pipeline: camera offset → world rotation → perspective → pixel space.
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
        (ux, vx), _ = self.project(meters(3.0, 0.0, 0.0))
        (uy, vy), _ = self.project(meters(0.0, 3.0, 0.0))
        (uz, vz), _ = self.project(meters(0.0, 0.0, 3.0))
        origin = (int(u0), int(v0))
        pygame.draw.line(surface, AXIS_COLOR, origin, (int(ux), int(vx)), 1)
        pygame.draw.line(surface, AXIS_COLOR, origin, (int(uy), int(vy)), 1)
        pygame.draw.line(surface, AXIS_COLOR, origin, (int(uz), int(vz)), 1)

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
        lines = [
            f"magnetar  t={float(self.world.time):.2f}s  n={len(self.world)}",
            "2D view of 3D space  |  Esc/close window/Ctrl+D/quit to exit",
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

    # -- pygame init / teardown -----------------------------------------------

    def _load_hud_font(self, size: int = DEFAULT_HUD_FONT_SIZE) -> pygame.font.Font:
        """Load the packaged bold HUD font (IBM Plex Sans Bold)."""
        font_path = self._font_session.open()
        return pygame.font.Font(str(font_path), size)

    def _init_pygame(self) -> None:
        """Initialize only the subsystems we need — never the audio mixer."""
        pygame.display.init()
        pygame.font.init()
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()

    def _shutdown_pygame(self) -> None:
        try:
            if pygame.mixer.get_init() is not None:
                pygame.mixer.quit()
        except Exception:
            pass
        try:
            pygame.display.quit()
        except Exception:
            pass
        try:
            pygame.font.quit()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass
        self.font = None
        self._font_session.close()
        self.screen = None
        self.clock = None


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point used by ``python -m magnetar`` and console scripts."""
    _ = list(argv) if argv is not None else sys.argv[1:]
    return MagnetarApp(world_factory=create_world).start()


if __name__ == "__main__":
    raise SystemExit(main())
