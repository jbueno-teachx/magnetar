# SPDX-License-Identifier: CC0-1.0
"""Button widgets and icon helpers."""

from __future__ import annotations

import math
import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.widgets.base import (
    AnchorLike,
    Command,
    EventInterest,
    Point,
    ScreenSize,
    Widget,
    WidgetPointerEvent,
)


class Button(Widget):
    """Clickable widget; ``command`` is invoked on click (button up as click)."""

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        *,
        anchor: AnchorLike = None,
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
            anchor=anchor,
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
        anchor: AnchorLike = None,
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
            anchor=anchor,
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
        (200, 340, 340),  # top arc, arrow pointing right-ish along top
        (290, 430, 70),  # right arc
        (20, 160, 160),  # bottom arc
        (110, 250, 250),  # left arc
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
