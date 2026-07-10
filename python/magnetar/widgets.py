# SPDX-License-Identifier: CC0-1.0
"""Minimal widget framework for in-window magnetar controls.

Coordinates are absolute screen percentages (0–100). A layout manager may
later own placement; for now each widget stores its own box.
"""

import enum
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Command = Callable[..., Any] | None
ScreenSize = tuple[int, int]  # (width, height)
Point = tuple[int, int]


class EventInterest(enum.Flag):
    """What kinds of mouse events a widget wants from the registry."""

    NONE = 0
    CLICK = enum.auto()
    MOVE = enum.auto()
    DRAG = enum.auto()
    ALL = CLICK | MOVE | DRAG


@dataclass(frozen=True, slots=True)
class WidgetPointerEvent:
    """Normalized pointer event delivered to widgets."""

    kind: str  # "down" | "up" | "move" | "drag" | "click"
    pos: Point  # screen pixels
    rel: Point = (0, 0)
    buttons: int = 0
    button: int = 0


# ---------------------------------------------------------------------------
# Base widget
# ---------------------------------------------------------------------------


class Widget:
    """UI element with a bounding box in *percent of the screen* (0–100)."""

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        *,
        command: Command = None,
        name: str = "",
        interest: EventInterest = EventInterest.CLICK,
        visible: bool = True,
        enabled: bool = True,
    ) -> None:
        self.x_pct = float(x_pct)
        self.y_pct = float(y_pct)
        self.w_pct = float(w_pct)
        self.h_pct = float(h_pct)
        self.command = command
        self.name = name or type(self).__name__
        self.interest = interest
        self.visible = visible
        self.enabled = enabled
        # Optional layout hook: when a layout manager exists it may set this.
        self.layout_managed = False

    def screen_rect(self, screen_size: ScreenSize) -> pygame.Rect:
        """Pixel rect for the current screen size (absolute percent placement)."""
        sw, sh = screen_size
        return pygame.Rect(
            int(round(self.x_pct / 100.0 * sw)),
            int(round(self.y_pct / 100.0 * sh)),
            max(1, int(round(self.w_pct / 100.0 * sw))),
            max(1, int(round(self.h_pct / 100.0 * sh))),
        )

    def hit_test(self, pos: Point, screen_size: ScreenSize) -> bool:
        if not self.visible or not self.enabled:
            return False
        return self.screen_rect(screen_size).collidepoint(pos)

    def draw(self, surface: pygame.Surface) -> None:
        """Override to paint the widget."""

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        """Handle a pointer event. Return True if consumed."""
        return False

    def invoke_command(self, *args: Any, **kwargs: Any) -> None:
        if self.command is not None:
            self.command(*args, **kwargs)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


class Button(Widget):
    """Clickable widget; ``command`` is invoked on click (button up as click)."""

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        *,
        command: Command = None,
        name: str = "",
        interest: EventInterest = EventInterest.CLICK,
        label: str = "",
        fill: tuple[int, int, int, int] | None = (20, 40, 40, 180),
        border: tuple[int, int, int] = (0, 255, 255),
    ) -> None:
        super().__init__(
            x_pct,
            y_pct,
            w_pct,
            h_pct,
            command=command,
            name=name,
            interest=interest,
        )
        self.label = label
        self.fill = fill
        self.border = border
        self._pressed = False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        rect = self.screen_rect(surface.get_size())
        if self.fill is not None:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(self.fill)
            surface.blit(overlay, rect.topleft)
        pygame.draw.rect(surface, self.border, rect, width=1, border_radius=4)

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        if event.kind == "down" and event.button == 1:
            self._pressed = True
            return True
        if event.kind == "click" and event.button == 1:
            self._pressed = False
            self.invoke_command()
            return True
        if event.kind == "up":
            self._pressed = False
        return False


class DragImageButton(Button):
    """Image button that supports drag (capture while pressed) and click.

    Drag may start inside the widget and continue outside until button-up.
    Clicks that don't move past the drag threshold invoke ``command`` with
    the quadrant name of the press position: ``"up" | "down" | "left" | "right"``.
    """

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        image: pygame.Surface,
        *,
        command: Command = None,
        on_drag: Command = None,
        name: str = "",
        drag_threshold_px: int = 6,
    ) -> None:
        super().__init__(
            x_pct,
            y_pct,
            w_pct,
            h_pct,
            command=command,
            name=name,
            interest=EventInterest.CLICK | EventInterest.DRAG,
        )
        self.image = image
        self.on_drag = on_drag
        self.drag_threshold_px = drag_threshold_px
        self._drag_origin: Point | None = None
        self._dragging = False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        rect = self.screen_rect(surface.get_size())
        if self.fill is not None:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(self.fill)
            surface.blit(overlay, rect.topleft)
        scaled = pygame.transform.smoothscale(self.image, rect.size)
        surface.blit(scaled, rect.topleft)
        pygame.draw.rect(surface, self.border, rect, width=1, border_radius=4)

    @staticmethod
    def zone_at(
        pos: Point,
        rect: pygame.Rect,
        *,
        center_manhattan: float = 0.10,
    ) -> str:
        """Hit zone: ``center`` or a quadrant (``up``/``down``/``left``/``right``).

        Center uses Manhattan measure in units of half-width / half-height:
        ``|nx| + |ny| <= center_manhattan`` (default 10% of the way to the edges).
        """
        cx, cy = rect.center
        hw = max(rect.width / 2.0, 1e-6)
        hh = max(rect.height / 2.0, 1e-6)
        nx = (pos[0] - cx) / hw
        ny = (pos[1] - cy) / hh
        if abs(nx) + abs(ny) <= center_manhattan:
            return "center"
        if abs(nx) >= abs(ny):
            return "right" if nx >= 0 else "left"
        return "down" if ny >= 0 else "up"

    @staticmethod
    def quadrant_at(pos: Point, rect: pygame.Rect) -> str:
        """Which of the four quadrants contains ``pos`` (relative to rect center)."""
        zone = DragImageButton.zone_at(pos, rect, center_manhattan=0.0)
        return "up" if zone == "center" else zone

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        rect = self.screen_rect(screen_size)

        if event.kind == "down" and event.button == 1:
            self._pressed = True
            self._dragging = False
            self._drag_origin = event.pos
            return True

        if event.kind == "drag" and self._pressed and self._drag_origin is not None:
            ox, oy = self._drag_origin
            total_dx = event.pos[0] - ox
            total_dy = event.pos[1] - oy
            if not self._dragging:
                if math.hypot(total_dx, total_dy) >= self.drag_threshold_px:
                    self._dragging = True
                else:
                    return True
            if self.on_drag is not None:
                self.on_drag(event.rel[0], event.rel[1], total_dx, total_dy)
            return True

        if event.kind == "up" and event.button == 1:
            was_dragging = self._dragging
            origin = self._drag_origin
            self._pressed = False
            self._dragging = False
            self._drag_origin = None
            # Click = press released without becoming a drag. Use press origin for zone.
            if not was_dragging and origin is not None:
                zone = self.zone_at(origin, rect)
                self.invoke_command(zone)
            return True

        if event.kind == "click" and event.button == 1:
            # Click already handled on button-up for this control.
            return True

        return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WidgetRegistry:
    """Owns widgets and dispatches pygame mouse events to them."""

    def __init__(self) -> None:
        self._widgets: list[Widget] = []
        self._capture: Widget | None = None  # drag capture
        self._down_widget: Widget | None = None
        self._down_pos: Point | None = None

    def add(self, widget: Widget) -> Widget:
        self._widgets.append(widget)
        return widget

    def remove(self, widget: Widget) -> None:
        if widget in self._widgets:
            self._widgets.remove(widget)
        if self._capture is widget:
            self._capture = None
        if self._down_widget is widget:
            self._down_widget = None

    def clear(self) -> None:
        self._widgets.clear()
        self._capture = None
        self._down_widget = None

    def __iter__(self) -> Iterable[Widget]:
        return iter(self._widgets)

    @property
    def interest_mask(self) -> EventInterest:
        """Union of interests of enabled, visible widgets (and active capture)."""
        mask = EventInterest.NONE
        for w in self._widgets:
            if w.visible and w.enabled:
                mask |= w.interest
        if self._capture is not None:
            mask |= EventInterest.DRAG | EventInterest.MOVE
        return mask

    def wants_event(self, event: pygame.event.Event) -> bool:
        """Fast gate: whether any widget might care about this pygame event."""
        mask = self.interest_mask
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return bool(mask & (EventInterest.CLICK | EventInterest.DRAG))
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return bool(mask & (EventInterest.CLICK | EventInterest.DRAG)) or self._capture is not None
        if event.type == pygame.MOUSEMOTION:
            if event.buttons[0] and (mask & EventInterest.DRAG or self._capture is not None):
                return True
            return bool(mask & EventInterest.MOVE)
        return False

    def widget_at(self, pos: Point, screen_size: ScreenSize) -> Widget | None:
        # Topmost = last added
        for widget in reversed(self._widgets):
            if widget.hit_test(pos, screen_size):
                return widget
        return None

    def dispatch(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        """Dispatch one pygame event. Returns True if a widget consumed it."""
        if not self.wants_event(event):
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            widget = self.widget_at(pos, screen_size)
            if widget is None:
                return False
            self._down_widget = widget
            self._down_pos = pos
            if widget.interest & EventInterest.DRAG:
                self._capture = widget
            pe = WidgetPointerEvent(kind="down", pos=pos, button=1, buttons=1)
            return widget.on_event(pe, screen_size)

        if event.type == pygame.MOUSEMOTION:
            pos = event.pos
            rel = event.rel
            buttons = 1 if event.buttons[0] else 0
            if self._capture is not None and event.buttons[0]:
                pe = WidgetPointerEvent(
                    kind="drag", pos=pos, rel=rel, buttons=buttons, button=1
                )
                return self._capture.on_event(pe, screen_size)
            if self.interest_mask & EventInterest.MOVE:
                widget = self.widget_at(pos, screen_size)
                if widget is not None and widget.interest & EventInterest.MOVE:
                    pe = WidgetPointerEvent(kind="move", pos=pos, rel=rel, buttons=buttons)
                    return widget.on_event(pe, screen_size)
            return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pos = event.pos
            target = self._capture or self._down_widget
            self._capture = None
            down_widget = self._down_widget
            down_pos = self._down_pos
            self._down_widget = None
            self._down_pos = None
            if target is None:
                return False
            # Click if press & release on same widget (or capture) without leaving as drag-only.
            pe_up = WidgetPointerEvent(kind="up", pos=pos, button=1, buttons=0)
            target.on_event(pe_up, screen_size)
            if down_widget is target and down_pos is not None:
                pe_click = WidgetPointerEvent(kind="click", pos=pos, button=1, buttons=0)
                return target.on_event(pe_click, screen_size)
            return True

        return False

    def draw(self, surface: pygame.Surface) -> None:
        for widget in self._widgets:
            if widget.visible:
                widget.draw(surface)


# ---------------------------------------------------------------------------
# Icon factory
# ---------------------------------------------------------------------------


def make_curved_arrows_icon(
    size: int = 128,
    *,
    color: tuple[int, int, int] = (0, 255, 255),
    accent: tuple[int, int, int] = (0, 180, 180),
) -> pygame.Surface:
    """Draw four curved orbital arrows (one per quadrant) on a transparent surface."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    radius = int(size * 0.32)
    width = max(2, size // 28)

    # Soft disc background
    pygame.draw.circle(surf, (*accent, 40), (cx, cy), int(size * 0.46))
    pygame.draw.circle(surf, (*color, 60), (cx, cy), int(size * 0.46), width=1)

    def arrow_head(tip: tuple[float, float], angle: float, scale: float = 1.0) -> None:
        length = size * 0.07 * scale
        spread = math.radians(28)
        pts = [
            tip,
            (
                tip[0] - length * math.cos(angle - spread),
                tip[1] - length * math.sin(angle - spread),
            ),
            (
                tip[0] - length * math.cos(angle + spread),
                tip[1] - length * math.sin(angle + spread),
            ),
        ]
        pygame.draw.polygon(surf, color, [(int(x), int(y)) for x, y in pts])

    # Four arcs centered on mid-angles of each quadrant-ish orbit directions.
    # Top (yaw-ish leftward curve), right, bottom, left — decorative orbit cues.
    arcs: list[tuple[float, float, float]] = [
        # (start_deg, end_deg, head_tangent_deg)  pygame: 0° right, CCW
        (200, 340, 340),   # top arc, arrow pointing right-ish along top
        (290, 430, 70),    # right arc
        (20, 160, 160),    # bottom arc
        (110, 250, 250),   # left arc
    ]
    box = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
    for start, end, head_deg in arcs:
        pygame.draw.arc(surf, color, box, math.radians(start), math.radians(end), width)
        # Arrow head at end of arc
        a = math.radians(head_deg)
        tip = (cx + radius * math.cos(a), cy - radius * math.sin(a))
        # Tangent direction for CCW arc head
        tangent = a + math.pi / 2
        arrow_head(tip, -tangent + math.pi)  # adjust to point along arc

    # Center crosshair (look-at origin cue)
    gap = size // 14
    pygame.draw.line(surf, color, (cx - gap, cy), (cx + gap, cy), 1)
    pygame.draw.line(surf, color, (cx, cy - gap), (cx, cy + gap), 1)
    return surf
