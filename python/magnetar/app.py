# SPDX-License-Identifier: CC0-1.0
"""Magnetar application: pygame 2D view of the 3D particle world.

View options are hardcoded here for now; camera and simulation controls
will grow around these defaults.
"""

import math
import os
import sys
from typing import Callable, Iterable, Sequence, Tuple

# Do not let SDL open a real audio device — pygame.init() would otherwise
# initialize the mixer and can pause / preempt other apps' playback.
# This is unrelated to OpenGL; it is the SDL audio subsystem.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.assets import DEFAULT_HUD_FONT_SIZE, hud_font_path
from magnetar.prompt import InteractivePrompt
from magnetar.units import coulomb, gram, meters, second
from magnetar.view3d import ViewCamera
from magnetar import widgets as widgets_pkg
from magnetar.widgets import (
    Anchor,
    DragImageButton,
    TextEntry,
    WIDGET_SUBMIT,
    WidgetRegistry,
    make_curved_arrows_icon,
)
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
PARTICLE_RADIUS_PX = 16
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
# Anchor point = bottom-right of the control (margin from window edges).
UI_MARGIN_PCT = 2.0
ROTATE_WIDGET_X_PCT = 100.0 - UI_MARGIN_PCT  # right edge
ROTATE_WIDGET_Y_PCT = 100.0 - UI_MARGIN_PCT  # bottom edge
ROTATE_WIDGET_ANCHOR = Anchor(h="right", v="bottom")

# In-window command line — same bottom edge as the orbit control.
PROMPT_WIDGET_H_PCT = 4.5
PROMPT_WIDGET_X_PCT = 1.0  # left edge
PROMPT_WIDGET_Y_PCT = ROTATE_WIDGET_Y_PCT  # shared bottom with orbit button
PROMPT_WIDGET_ANCHOR = Anchor(h="left", v="bottom")
# Stretch almost to the orbit control's left edge (orbit is right-anchored).
PROMPT_WIDGET_W_PCT = (ROTATE_WIDGET_X_PCT - ROTATE_WIDGET_W_PCT) - PROMPT_WIDGET_X_PCT - 1.0

# pygame KEYDOWN auto-repeat while a key is held (TextEntry, etc.).
# delay = ms before first repeat; interval = ms between subsequent repeats.
KEY_REPEAT_DELAY_MS = 400
KEY_REPEAT_INTERVAL_MS = 35


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
        color="yellow",
        label="E+",
    )
    world.add_electro(
        meters(2.0, 0.0, 0.0),
        charge=coulomb(-1.0),
        mass=gram(1.0),
        velocity=(-0.2, 0.1, 0.0),  # m/s
        color="light_blue",
        label="E-",
    )
    # Bound charge: fixed in place, field source only.
    world.add_electro(
        meters(0.0, 1.5, 1.0),
        charge=coulomb(2.0),
        mass=gram(5.0),
        pinned=True,
        color="red",
        label="Efix",
    )
    return world


class MagnetarApp:
    """pygame front-end: owns the world, prompt, projection, and main loop."""

    def __init__(self, world_factory: WorldFactory = create_world) -> None:
        self.world_factory = world_factory
        self.world: World = world_factory()
        # World keeps the app via a per-instance ContextVar (ScreenSprite → World → App).
        self.world.bind_app(self)
        self.prompt = InteractivePrompt(self.world)

        # 3D view / orbit / projection (associated object, not mixed into App).
        self.view = ViewCamera(
            camera_offset=CAMERA_OFFSET,
            world_scale=WORLD_SCALE,
            perspective=PERSPECTIVE,
            viewport_size=(VIEW_WIDTH, VIEW_HEIGHT),
        )
        self.particle_radius_px: int = PARTICLE_RADIUS_PX

        # pygame resources (filled in by start / _init_pygame)
        self.screen: pygame.Surface | None = None
        self.clock: pygame.time.Clock | None = None
        self.font: pygame.font.Font | None = None
        self.running: bool = False
        self.tick: int = 0  # animation clock; ScreenSprite wraps frames with this

        # In-window UI (registry filled after pygame init when surfaces exist).
        self.widgets = WidgetRegistry()
        self._orbit_button: DragImageButton | None = None
        self._prompt_entry: TextEntry | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> int:
        """Initialize, run the loop, always shut down cleanly."""
        self._init()
        try:
            return self.run()
        finally:
            self._quit()

    def _init(self) -> None:
        """Bring up pygame, widgets (clipboard), display, UI, and stdin prompt."""
        self._init_pygame()
        widgets_pkg.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.screen = pygame.display.set_mode((VIEW_WIDTH, VIEW_HEIGHT))
        self.view.viewport_size = self.screen.get_size()
        self.clock = pygame.time.Clock()
        with hud_font_path() as font_file:
            self.font = pygame.font.Font(str(font_file), DEFAULT_HUD_FONT_SIZE)
        self._build_ui()
        self.prompt.start()

    def _quit(self) -> None:
        """Tear down prompt, widgets (clipboard), and pygame."""
        self.prompt.stop()
        widgets_pkg.quit()
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
            self.tick += 1
        return 0

    def events(self) -> None:
        """Poll pygame events, widget registry, and the interactive prompt."""
        screen_size = (
            self.screen.get_size() if self.screen is not None else (VIEW_WIDTH, VIEW_HEIGHT)
        )
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue

            # Generic widget signals (usable by any Widget subclass).
            if event.type == WIDGET_SUBMIT:
                self._on_widget_submit(event)
                continue

            # Mouse / key → widget registry first (focused TextEntry eats typing).
            if event.type in (
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.KEYDOWN,
            ):
                if self.widgets.dispatch(event, screen_size):
                    continue

            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE,
                pygame.K_q,
            ):
                self.running = False
                continue

        if self.prompt.poll() is False:
            self.running = False

    def _on_widget_submit(self, event: pygame.event.Event) -> None:
        """Handle :data:`~magnetar.widgets.WIDGET_SUBMIT` (not wired to REPL yet)."""
        text = getattr(event, "text", None)
        if text is None and getattr(event, "widget", None) is not None:
            text = getattr(event.widget, "text", "")
        line = "" if text is None else str(text)
        # Temporary observability for the in-window line; REPL wiring comes later.
        print(line, flush=True)
        if self._prompt_entry is not None and getattr(event, "widget", None) is self._prompt_entry:
            self._prompt_entry.clear(notify=False)

    # -- view API proxies (delegate to self.view) ------------------------------

    @property
    def view_matrix(self):
        return self.view.view_matrix

    @view_matrix.setter
    def view_matrix(self, value) -> None:
        self.view.view_matrix = value

    @property
    def world_rotation(self) -> Vec3f:
        return self.view.world_rotation

    @world_rotation.setter
    def world_rotation(self, ypr: Sequence[float]) -> None:
        self.view.world_rotation = ypr

    @property
    def camera_offset(self) -> Vec3f:
        return self.view.camera_offset

    @camera_offset.setter
    def camera_offset(self, value: Vec3f) -> None:
        self.view.camera_offset = value

    @property
    def world_scale(self) -> float:
        return self.view.world_scale

    @world_scale.setter
    def world_scale(self, value: float) -> None:
        self.view.world_scale = float(value)

    @property
    def perspective(self) -> float:
        return self.view.perspective

    @perspective.setter
    def perspective(self, value: float) -> None:
        self.view.perspective = float(value)

    def project(
        self,
        point: Sequence[float],
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> Tuple[Vec2, float]:
        """Project via :attr:`view` (viewport defaults to the live screen size)."""
        if width is None or height is None:
            if self.screen is not None:
                sw, sh = self.screen.get_size()
                width = width if width is not None else sw
                height = height if height is not None else sh
            else:
                width = width if width is not None else VIEW_WIDTH
                height = height if height is not None else VIEW_HEIGHT
        return self.view.project(point, width=width, height=height)

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
            "orbit: drag / click sides; center resets  |  click bottom line to type  |  Esc/q quit",
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

        # Painter order via LayeredUpdates: larger depth (farther) draws first.
        group = self.world.particles
        for sprite in group:
            if hasattr(sprite, "view_depth"):
                depth = sprite.view_depth()
            else:
                _uv, depth = self.project(getattr(sprite, "position", (0, 0, 0)))
            group.change_layer(sprite, int(-float(depth) * 1000.0))
        # Group.draw blits each sprite.image at sprite.rect (ScreenSprite properties).
        group.draw(self.screen)

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
            anchor=ROTATE_WIDGET_ANCHOR,
            name="orbit",
            command=self._on_orbit_click,
            on_drag=self._on_orbit_drag,
        )
        self.widgets.add(self._orbit_button)

        self._prompt_entry = TextEntry(
            PROMPT_WIDGET_X_PCT,
            PROMPT_WIDGET_Y_PCT,
            PROMPT_WIDGET_W_PCT,
            PROMPT_WIDGET_H_PCT,
            anchor=PROMPT_WIDGET_ANCHOR,
            font=self.font,
            name="prompt",
            placeholder="magnetar> ",
            border=THEME_COLOR,
            border_focused=(0, 255, 200),
            text_color=THEME_COLOR,
            placeholder_color=(0, 120, 120),
            caret_color=THEME_COLOR,
        )
        self.widgets.add(self._prompt_entry)
        # Ready for typing without an extra click during this experiment.
        self.widgets.set_focus(self._prompt_entry)

    def _on_orbit_click(self, zone: str) -> None:
        """Discrete orbit step from the *current* orientation, or reset on center.

        Side zones apply ±10° about the current view axes (camera-relative).
        Center (Manhattan ≤ 10% of half-size) resets to identity.
        """
        if zone == "center":
            self.view.reset()
            return
        step = math.radians(ROTATE_CLICK_DEGREES)
        if zone == "left":
            self.view.orbit_camera(-step, 0.0)
        elif zone == "right":
            self.view.orbit_camera(step, 0.0)
        elif zone == "up":
            self.view.orbit_camera(0.0, step)
        elif zone == "down":
            self.view.orbit_camera(0.0, -step)

    def _on_orbit_drag(self, dx: int, dy: int, total_dx: int, total_dy: int) -> None:
        """Continuous camera-relative orbit (drag may leave the widget)."""
        _ = (total_dx, total_dy)
        sens = math.radians(ROTATE_DRAG_DEGREES_PER_PIXEL)
        self.view.orbit_camera(dx * sens, -dy * sens)

    # -- pygame init / teardown -----------------------------------------------

    def _init_pygame(self) -> None:
        """Initialize only the subsystems we need — never the audio mixer."""
        pygame.display.init()
        pygame.font.init()
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()
        # Held keys re-fire KEYDOWN (printable, arrows, backspace, …) for TextEntry.
        pygame.key.set_repeat(KEY_REPEAT_DELAY_MS, KEY_REPEAT_INTERVAL_MS)

    def _shutdown_pygame(self) -> None:
        try:
            pygame.key.set_repeat()  # disable
        except pygame.error:
            pass
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
