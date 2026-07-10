"""Magnetar application: pygame 2D view of the 3D particle world.

View options are hardcoded here for now; camera and simulation controls
will grow around these defaults.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, List, Sequence, Tuple

# Do not let SDL open a real audio device — pygame.init() would otherwise
# initialize the mixer and can pause / preempt other apps' playback.
# This is unrelated to OpenGL; it is the SDL audio subsystem.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

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

# Orthographic-ish scale: world units → pixels (before perspective foreshortening).
WORLD_SCALE = 80.0
# Simple perspective: divides x/y by (1 + z * PERSPECTIVE).
PERSPECTIVE = 0.08
# Camera look-at origin offset in world space.
CAMERA_OFFSET = (0.0, 0.0, 0.0)

# Particle drawing
PARTICLE_RADIUS_PX = 8
ELECTRO_COLOR = THEME_COLOR
BOUND_COLOR = (255, 200, 64)  # fixed field sources
NEUTRAL_COLOR = (160, 160, 160)
AXIS_COLOR = (0, 80, 80)
HUD_COLOR = THEME_COLOR


Vec2 = Tuple[float, float]


def project(point: Sequence[float], *, width: int, height: int) -> Tuple[Vec2, float]:
    """Project a 3D world point (meters) to 2D screen coordinates.

    Returns ``((sx, sy), depth)`` where larger depth is farther from the camera
    (used for painter's algorithm draw order). Depth is the z coordinate in m.
    """
    ox, oy, oz = CAMERA_OFFSET
    x = float(point[0]) - ox
    y = float(point[1]) - oy
    z = float(point[2]) - oz

    # Perspective foreshortening along +z (into the screen).
    factor = 1.0 / max(0.2, 1.0 + z * PERSPECTIVE)
    sx = width * 0.5 + x * WORLD_SCALE * factor
    sy = height * 0.5 - y * WORLD_SCALE * factor  # y up in world → up on screen
    return (sx, sy), z


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


def draw_axes(surface: pygame.Surface) -> None:
    """Draw X/Y axes and a faint unit grid cross at the origin."""
    w, h = surface.get_size()
    cx, cy = w // 2, h // 2
    pygame.draw.line(surface, AXIS_COLOR, (0, cy), (w, cy), 1)
    pygame.draw.line(surface, AXIS_COLOR, (cx, 0), (cx, h), 1)
    # short Z hint (diagonal)
    (zx, zy), _ = project(meters(0.0, 0.0, 3.0), width=w, height=h)
    pygame.draw.line(surface, AXIS_COLOR, (cx, cy), (int(zx), int(zy)), 1)


def draw_particle(surface: pygame.Surface, particle: Particle, pos: Vec2) -> None:
    x, y = int(pos[0]), int(pos[1])
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
        pygame.draw.circle(surface, color, (x, y), r, width=width)
        # charge sign
        pygame.draw.line(surface, color if width else BACKGROUND_COLOR, (x - r // 2, y), (x + r // 2, y), 2)
        if particle.charge >= 0:
            pygame.draw.line(
                surface,
                color if width else BACKGROUND_COLOR,
                (x, y - r // 2),
                (x, y + r // 2),
                2,
            )
        if particle.pinned:
            # small outer ring marks a pinned (immobile) source
            pygame.draw.circle(surface, color, (x, y), r + 3, width=1)
    else:
        # neutral / base particle
        pygame.draw.circle(surface, color, (x, y), r // 2, width=0 if particle.pinned else 1)


def draw_hud(surface: pygame.Surface, world: World, font: pygame.font.Font) -> None:
    lines = [
        f"magnetar  t={float(world.time):.2f}s  n={len(world)}",
        "2D view of 3D space  |  Esc/close window/Ctrl+D/quit to exit",
    ]
    y = 8
    for line in lines:
        text = font.render(line, True, HUD_COLOR)
        surface.blit(text, (10, y))
        y += text.get_height() + 2


def render_frame(
    surface: pygame.Surface,
    world: World,
    font: pygame.font.Font,
) -> None:
    surface.fill(BACKGROUND_COLOR)
    draw_axes(surface)

    projected: List[Tuple[float, Particle, Vec2]] = []
    for p in world.particles:
        screen_pos, depth = project(
            p.position, width=surface.get_width(), height=surface.get_height()
        )
        projected.append((depth, p, screen_pos))
    # Far particles first.
    projected.sort(key=lambda item: item[0], reverse=True)
    for _, particle, pos in projected:
        draw_particle(surface, particle, pos)

    draw_hud(surface, world, font)


def _init_pygame() -> None:
    """Initialize only the subsystems we need — never the audio mixer."""
    # Belt-and-suspenders with SDL_AUDIODRIVER=dummy above.
    pygame.display.init()
    pygame.font.init()
    # If something else pulled mixer in, release it immediately.
    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()


def _shutdown_pygame() -> None:
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


def run(world: World | None = None) -> int:
    """Create the 2D view window and run the main loop. Returns a process exit code."""
    world = world if world is not None else create_world()
    prompt: InteractivePrompt | None = None

    _init_pygame()
    try:
        pygame.display.set_caption(WINDOW_TITLE)
        screen = pygame.display.set_mode((VIEW_WIDTH, VIEW_HEIGHT))
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("monospace", 16)

        prompt = InteractivePrompt(world)
        prompt.start()

        running = True
        while running:
            dt_ms = clock.tick(TARGET_FPS)
            dt = second(dt_ms / 1000.0)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE,
                    pygame.K_q,
                ):
                    running = False

            if prompt.poll() is False:
                running = False

            if not running:
                break

            world.step(dt)
            render_frame(screen, world, font)
            pygame.display.flip()
    finally:
        if prompt is not None:
            prompt.stop()
        _shutdown_pygame()

    return 0


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point used by ``python -m magnetar`` and console scripts."""
    _ = list(argv) if argv is not None else sys.argv[1:]
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
