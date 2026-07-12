# SPDX-License-Identifier: CC0-1.0
"""Base widget types, anchors, and generic widget pygame events."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Union
import enum

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

Command = Callable[..., Any] | None
ScreenSize = tuple[int, int]  # (width, height)
Point = tuple[int, int]


class AnchorH(enum.StrEnum):
    """Horizontal attachment of the widget box to ``x_pct``."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class AnchorV(enum.StrEnum):
    """Vertical attachment of the widget box to ``y_pct``."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class Anchor:
    """Where ``(x_pct, y_pct)`` sits on the widget's bounding box.

    Examples::

        Anchor()                      # top-left (default)
        Anchor(h="right", v="bottom") # bottom-right
        Anchor.parse("midbottom")
        Anchor.parse(("center", "bottom"))
    """

    h: AnchorH = AnchorH.LEFT
    v: AnchorV = AnchorV.TOP

    def __post_init__(self) -> None:
        # Normalize string inputs from callers.
        object.__setattr__(self, "h", AnchorH(str(self.h).lower()))
        object.__setattr__(self, "v", AnchorV(str(self.v).lower()))

    @classmethod
    def parse(cls, value: Union["Anchor", str, tuple[str, str], None] = None) -> "Anchor":
        if value is None:
            return cls()
        if isinstance(value, Anchor):
            return value
        if isinstance(value, tuple) and len(value) == 2:
            return cls(h=value[0], v=value[1])
        if not isinstance(value, str):
            raise TypeError(f"unsupported anchor: {value!r}")
        key = value.strip().lower().replace("-", "").replace("_", "")
        aliases: dict[str, tuple[str, str]] = {
            "topleft": ("left", "top"),
            "topright": ("right", "top"),
            "bottomleft": ("left", "bottom"),
            "bottomright": ("right", "bottom"),
            "midtop": ("center", "top"),
            "midbottom": ("center", "bottom"),
            "midleft": ("left", "center"),
            "midright": ("right", "center"),
            "center": ("center", "center"),
            "centre": ("center", "center"),
        }
        if key in aliases:
            h, v = aliases[key]
            return cls(h=h, v=v)
        # "left,bottom" / "right bottom"
        parts = [p for p in key.replace(",", " ").split() if p]
        if len(parts) == 2:
            # Allow either order: ("bottom", "left") or ("left", "bottom").
            a, b = parts[0], parts[1]
            hs = {e.value for e in AnchorH}
            vs = {e.value for e in AnchorV}
            if a in hs and b in vs:
                return cls(h=a, v=b)
            if a in vs and b in hs:
                return cls(h=b, v=a)
        raise ValueError(f"unknown anchor {value!r}")


AnchorLike = Union[Anchor, str, tuple[str, str], None]


class EventInterest(enum.Flag):
    """What kinds of events a widget wants from the registry."""

    NONE = 0
    CLICK = enum.auto()
    MOVE = enum.auto()
    DRAG = enum.auto()
    KEY = enum.auto()
    ALL = CLICK | MOVE | DRAG | KEY


# Generic custom pygame events for *any* widget subclass (post via
# :meth:`Widget.post_event`). Attribute payload always includes ``widget``
# and ``name``; subclasses may add fields (e.g. ``text``, ``cursor``, ``value``).
WIDGET_CHANGED = pygame.event.custom_type()  # value / content mutated
WIDGET_SUBMIT = pygame.event.custom_type()  # primary confirm action (Enter, …)
WIDGET_FOCUS = pygame.event.custom_type()  # gained keyboard / input focus
WIDGET_BLUR = pygame.event.custom_type()  # lost focus


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
    """UI element with a bounding box in *percent of the screen* (0–100).

    ``(x_pct, y_pct)`` locate the :attr:`anchor` point (default top-left of the
    box). Size is ``(w_pct, h_pct)``.
    """

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
        visible: bool = True,
        enabled: bool = True,
    ) -> None:
        self.x_pct = float(x_pct)
        self.y_pct = float(y_pct)
        self.w_pct = float(w_pct)
        self.h_pct = float(h_pct)
        self.anchor = Anchor.parse(anchor)
        self.command = command
        self.name = name or type(self).__name__
        self.interest = interest
        self.visible = visible
        self.enabled = enabled
        # Optional layout hook: when a layout manager exists it may set this.
        self.layout_managed = False

    def screen_rect(self, screen_size: ScreenSize) -> pygame.Rect:
        """Pixel rect for the current screen size (anchor-aware percent placement)."""
        sw, sh = screen_size
        width = max(1, int(round(self.w_pct / 100.0 * sw)))
        height = max(1, int(round(self.h_pct / 100.0 * sh)))
        ax = self.x_pct / 100.0 * sw
        ay = self.y_pct / 100.0 * sh

        if self.anchor.h is AnchorH.LEFT:
            left = ax
        elif self.anchor.h is AnchorH.CENTER:
            left = ax - width / 2.0
        else:  # RIGHT
            left = ax - width

        if self.anchor.v is AnchorV.TOP:
            top = ay
        elif self.anchor.v is AnchorV.CENTER:
            top = ay - height / 2.0
        else:  # BOTTOM
            top = ay - height

        return pygame.Rect(int(round(left)), int(round(top)), width, height)

    def hit_test(self, pos: Point, screen_size: ScreenSize) -> bool:
        if not self.visible or not self.enabled:
            return False
        return self.screen_rect(screen_size).collidepoint(pos)

    def draw(self, surface: pygame.Surface) -> None:
        """Override to paint the widget."""

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        """Handle a pointer event. Return True if consumed."""
        return False

    def handle_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        """Handle a ``KEYDOWN`` while this widget has registry focus.

        Return True if consumed. Default: ignore.
        """
        return False

    def invoke_command(self, *args: Any, **kwargs: Any) -> None:
        if self.command is not None:
            self.command(*args, **kwargs)

    def post_event(self, event_type: int, **payload: Any) -> None:
        """Post a generic widget event onto the pygame queue.

        Always sets ``widget`` (self) and ``name``. Extra keyword args become
        event attributes (e.g. ``text=…``, ``value=…``) for app handlers.
        """
        pygame.event.post(
            pygame.event.Event(
                event_type,
                widget=self,
                name=self.name,
                **payload,
            )
        )
