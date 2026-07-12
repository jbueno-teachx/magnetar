# SPDX-License-Identifier: CC0-1.0
"""Minimal widget framework for in-window magnetar controls.

Coordinates are absolute screen percentages (0–100). Placement uses an
:class:`Anchor`: ``(x_pct, y_pct)`` is the anchor point on the screen, and
the widget's box is laid out from that point (default top-left, legacy).
"""

import enum
import math
import os
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Union

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.clipboard import ClipboardError, get_text, set_text

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Named key bindings (Emacs / readline style, reusable by any widget)
# ---------------------------------------------------------------------------


class _ModSentinel:
    """Modifier marker used in :class:`KeyEvent` combo tuples."""

    __slots__ = ("name", "masks")

    def __init__(self, name: str, *masks: int) -> None:
        self.name = name
        self.masks = masks

    def present(self, mod: int) -> bool:
        return any(mod & m for m in self.masks)

    def __repr__(self) -> str:
        return f"KeyEvent.{self.name.upper()}"


class KeyEvent:
    """Named logical key action with one or more physical combos.

    Instantiation registers the binding in :attr:`mapping` (case-insensitive
    names). Lookup: ``KeyEvent["HOME"]`` / ``KeyEvent["home"]``.

    Combo forms (varargs to the constructor)::

        pygame.K_HOME                 # bare key
        "A"                           # letter key (case-insensitive)
        (KeyEvent.CTRL, "K")          # modifier + key
        (KeyEvent.ALT, pygame.K_BACKSPACE)

    Matching::

        if KeyEvent["HOME"].match(event):
            ...
        KeyEvent["HOME"].match(e1, e2)  # True if *any* event matches
    """

    # Modifier sentinels for combo tuples
    CTRL = _ModSentinel("ctrl", pygame.KMOD_CTRL)
    CONTROL = CTRL  # alias
    ALT = _ModSentinel("alt", pygame.KMOD_ALT)
    META = _ModSentinel("meta", pygame.KMOD_META, pygame.KMOD_GUI)
    SHIFT = _ModSentinel("shift", pygame.KMOD_SHIFT)

    # name.casefold() -> instance
    mapping: dict[str, "KeyEvent"] = {}

    # Bits treated as "chord modifiers" when a combo specifies none.
    _CHORD_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI

    def __init__(self, name: str, *combos: Any) -> None:
        if not name or not str(name).strip():
            raise ValueError("KeyEvent name must be non-empty")
        if not combos:
            raise ValueError(f"KeyEvent {name!r} needs at least one combo")
        self.name = str(name)
        self.combos: list[tuple[Any, ...]] = []
        for combo in combos:
            if isinstance(combo, tuple):
                if not combo:
                    raise ValueError(f"KeyEvent {name!r}: empty combo")
                self.combos.append(combo)
            else:
                # Bare key constant or letter string.
                self.combos.append((combo,))
        KeyEvent.mapping[self.name.casefold()] = self

    def __repr__(self) -> str:
        return f"KeyEvent({self.name!r}, …)"

    @classmethod
    def __class_getitem__(cls, name: str) -> "KeyEvent":
        try:
            return cls.mapping[str(name).casefold()]
        except KeyError as exc:
            raise KeyError(f"unknown KeyEvent {name!r}") from exc

    @classmethod
    def get(cls, name: str, default: "KeyEvent | None" = None) -> "KeyEvent | None":
        return cls.mapping.get(str(name).casefold(), default)

    @staticmethod
    def _token_to_key(token: Any) -> int | None:
        if isinstance(token, _ModSentinel):
            return None
        if isinstance(token, int):
            return int(token)
        if isinstance(token, str) and len(token) == 1:
            ch = token.lower()
            attr = f"K_{ch}"
            if hasattr(pygame, attr):
                return int(getattr(pygame, attr))
            # Digits and a few symbols via K_0 … if present
            return None
        if isinstance(token, str) and token.startswith("K_"):
            return int(getattr(pygame, token))
        return None

    def _match_combo(self, event: pygame.event.Event, combo: tuple[Any, ...]) -> bool:
        if getattr(event, "type", None) != pygame.KEYDOWN:
            return False
        mods = int(getattr(event, "mod", 0) or 0)
        required: list[_ModSentinel] = []
        key_code: int | None = None
        for part in combo:
            if isinstance(part, _ModSentinel):
                required.append(part)
                continue
            key_code = self._token_to_key(part)
            if key_code is None:
                return False
        if key_code is None or int(event.key) != key_code:
            return False
        for sentinel in required:
            if not sentinel.present(mods):
                return False
        if not required and (mods & self._CHORD_MODS):
            # Bare keys must not be part of a Ctrl/Alt/Meta chord.
            return False
        # When mods are required, still ignore if an *unrelated* chord family
        # is held without being listed (Ctrl vs Alt). Shift alone is fine.
        need_ctrl = any(s is KeyEvent.CTRL or s is KeyEvent.CONTROL for s in required)
        need_alt = any(s is KeyEvent.ALT for s in required)
        need_meta = any(s is KeyEvent.META for s in required)
        need_shift = any(s is KeyEvent.SHIFT for s in required)
        if required:
            if (mods & pygame.KMOD_CTRL) and not need_ctrl:
                return False
            # Alt without ALT/META in the combo is a different chord.
            if (mods & pygame.KMOD_ALT) and not need_alt and not need_meta:
                return False
            if (mods & (pygame.KMOD_META | pygame.KMOD_GUI)) and not need_meta and not need_alt:
                return False
            # Shift is optional unless the combo lists SHIFT (Ctrl+C still matches
            # Ctrl+Shift+C when only CTRL is required).
            if need_shift and not (mods & pygame.KMOD_SHIFT):
                return False
        return True

    def match(self, event: pygame.event.Event, *more: pygame.event.Event) -> bool:
        """Return True if any of the given pygame events matches this binding."""
        for ev in (event, *more):
            for combo in self.combos:
                if self._match_combo(ev, combo):
                    return True
        return False


# Logical bindings used by :class:`TextEntry` (and available app-wide).
KeyEvent("BACKWARD_CHAR", pygame.K_LEFT, (KeyEvent.CTRL, "B"))
KeyEvent("FORWARD_CHAR", pygame.K_RIGHT, (KeyEvent.CTRL, "F"))
KeyEvent("BACKWARD_WORD", (KeyEvent.ALT, "B"), (KeyEvent.META, "B"))
KeyEvent("FORWARD_WORD", (KeyEvent.ALT, "F"), (KeyEvent.META, "F"))
KeyEvent("HOME", pygame.K_HOME, (KeyEvent.CTRL, "A"))
KeyEvent("END", pygame.K_END, (KeyEvent.CTRL, "E"))
KeyEvent("BACKSPACE", pygame.K_BACKSPACE, (KeyEvent.CTRL, "H"))
KeyEvent("DELETE_CHAR", pygame.K_DELETE, (KeyEvent.CTRL, "D"))
KeyEvent("KILL_TO_END", (KeyEvent.CTRL, "K"))
KeyEvent("KILL_TO_START", (KeyEvent.CTRL, "U"))
KeyEvent(
    "KILL_WORD_BACKWARD",
    (KeyEvent.CTRL, "W"),
    (KeyEvent.ALT, pygame.K_BACKSPACE),
    (KeyEvent.META, pygame.K_BACKSPACE),
)
KeyEvent("KILL_WORD_FORWARD", (KeyEvent.ALT, "D"), (KeyEvent.META, "D"))
KeyEvent("YANK", (KeyEvent.CTRL, "Y"))
KeyEvent("TRANSPOSE", (KeyEvent.CTRL, "T"))
# System clipboard (full field until selection exists): Ctrl/Cmd+C, Ctrl+Shift+C.
KeyEvent(
    "COPY",
    (KeyEvent.CTRL, "C"),
    (KeyEvent.CTRL, KeyEvent.SHIFT, "C"),
    (KeyEvent.META, "C"),
)
KeyEvent(
    "PASTE",
    (KeyEvent.CTRL, "V"),
    (KeyEvent.META, "V"),
    (KeyEvent.SHIFT, pygame.K_INSERT),
)
KeyEvent("SUBMIT", pygame.K_RETURN, pygame.K_KP_ENTER)
KeyEvent("BLUR", pygame.K_ESCAPE)


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


# ---------------------------------------------------------------------------
# Text entry (single line)
# ---------------------------------------------------------------------------


class TextEntry(Widget):
    """Single-line text field with a ``|`` caret between characters.

    Keyboard handling runs only while :attr:`focused`. Length is limited so the
    rendered text fits the on-screen pixel width of the widget.

    Posts generic :data:`WIDGET_*` events (via :meth:`post_event`) with extra
    attributes ``text`` and ``cursor``.

    Emacs / GNU Readline-style bindings (implemented)
    -------------------------------------------------
    Movement::

        Ctrl+A / Home     beginning of line
        Ctrl+E / End      end of line
        Ctrl+B / ←        backward char
        Ctrl+F / →        forward char
        Alt+B             backward word
        Alt+F             forward word

    Deletion / kill (one-slot kill buffer for yank)::

        Ctrl+D / Delete   delete char under cursor
        Ctrl+H / Backspace  delete char before cursor
        Ctrl+K            kill to end of line
        Ctrl+U            kill to beginning of line
        Ctrl+W            kill word backward
        Alt+D             kill word forward
        Alt+Backspace     kill word backward
        Ctrl+Y            yank last kill (internal kill buffer)

    System clipboard (currently whole field; selection comes later)::

        Ctrl+C / Ctrl+Shift+C / Cmd+C   copy all text
        Ctrl+V / Cmd+V / Shift+Insert   paste at caret

    Other::

        Ctrl+T            transpose characters around cursor
        Enter             submit (``WIDGET_SUBMIT``)
        Esc               blur

    Not implemented (multi-line / history / full kill-ring / selection)::
    Ctrl+P/N history, Ctrl+_ undo, multi-entry kill ring, shift-move select.
    """

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        *,
        anchor: AnchorLike = None,
        font: pygame.font.Font | None = None,
        text: str = "",
        placeholder: str = "",
        name: str = "",
        command: Command = None,
        fill: tuple[int, int, int, int] | None = (12, 24, 28, 220),
        border: tuple[int, int, int] = (0, 255, 255),
        border_focused: tuple[int, int, int] = (0, 255, 200),
        text_color: tuple[int, int, int] = (0, 255, 255),
        placeholder_color: tuple[int, int, int] = (0, 120, 120),
        caret_color: tuple[int, int, int] = (0, 255, 255),
        padding_px: int = 8,
        caret_blink_ms: int = 530,
    ) -> None:
        super().__init__(
            x_pct,
            y_pct,
            w_pct,
            h_pct,
            anchor=anchor,
            command=command,
            name=name or "textentry",
            interest=EventInterest.CLICK | EventInterest.KEY,
        )
        self.font = font
        self._text = str(text)
        self.placeholder = placeholder
        self.fill = fill
        self.border = border
        self.border_focused = border_focused
        self.text_color = text_color
        self.placeholder_color = placeholder_color
        self.caret_color = caret_color
        self.padding_px = int(padding_px)
        self.caret_blink_ms = int(caret_blink_ms)
        self.focused = False
        self.cursor = len(self._text)
        self._caret_force_on_until: int = 0
        self._kill_buffer: str = ""

    # -- text / caret ---------------------------------------------------------

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = str(value)
        self.cursor = min(self.cursor, len(self._text))

    def set_font(self, font: pygame.font.Font | None) -> None:
        self.font = font

    def focus(self) -> None:
        if self.focused:
            return
        self.focused = True
        self._nudge_caret()
        self.post_event(WIDGET_FOCUS, text=self._text, cursor=self.cursor)

    def blur(self) -> None:
        if not self.focused:
            return
        self.focused = False
        self.post_event(WIDGET_BLUR, text=self._text, cursor=self.cursor)

    def clear(self, *, notify: bool = True) -> None:
        if not self._text and self.cursor == 0:
            return
        self._text = ""
        self.cursor = 0
        self._nudge_caret()
        if notify:
            self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)

    def _nudge_caret(self) -> None:
        """Keep the caret visible briefly after edits / moves."""
        self._caret_force_on_until = pygame.time.get_ticks() + self.caret_blink_ms

    def _content_width_budget(self, screen_size: ScreenSize) -> int:
        rect = self.screen_rect(screen_size)
        return max(0, rect.width - 2 * self.padding_px)

    def _text_pixel_width(self, s: str) -> int:
        if self.font is None:
            return len(s) * 8
        return self.font.size(s)[0]

    def _fits(self, s: str, screen_size: ScreenSize) -> bool:
        """Whether ``s`` fits the inner content width (caret drawn on top)."""
        return self._text_pixel_width(s) <= self._content_width_budget(screen_size)

    def _caret_visible(self) -> bool:
        if not self.focused:
            return False
        now = pygame.time.get_ticks()
        if now < self._caret_force_on_until:
            return True
        period = max(1, self.caret_blink_ms)
        return (now // period) % 2 == 0

    # -- drawing --------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        rect = self.screen_rect(surface.get_size())
        if self.fill is not None:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(self.fill)
            surface.blit(overlay, rect.topleft)
        border = self.border_focused if self.focused else self.border
        pygame.draw.rect(surface, border, rect, width=1, border_radius=3)

        if self.font is None:
            return

        inner_x = rect.x + self.padding_px
        inner_y = rect.y + max(0, (rect.height - self.font.get_height()) // 2)
        show_placeholder = (not self._text) and (not self.focused) and bool(self.placeholder)

        if show_placeholder:
            label = self.font.render(self.placeholder, True, self.placeholder_color)
            surface.blit(label, (inner_x, inner_y))
            return

        before = self._text[: self.cursor]
        after = self._text[self.cursor :]
        x = inner_x
        if before:
            img = self.font.render(before, True, self.text_color)
            surface.blit(img, (x, inner_y))
            x += img.get_width()

        if self._caret_visible():
            # Literal "|" caret between characters.
            caret = self.font.render("|", True, self.caret_color)
            cx = x - caret.get_width() // 2
            surface.blit(caret, (cx, inner_y))
            x = max(x, cx + caret.get_width() // 2)

        if after:
            img = self.font.render(after, True, self.text_color)
            surface.blit(img, (x, inner_y))

    # -- pointer / keyboard ---------------------------------------------------

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        if event.kind == "down" and event.button == 1:
            return True
        if event.kind == "click" and event.button == 1:
            self.focus()
            if self.font is not None:
                rect = self.screen_rect(screen_size)
                local_x = event.pos[0] - rect.x - self.padding_px
                self.cursor = self._index_for_x(local_x)
                self._nudge_caret()
            return True
        return False

    def _index_for_x(self, local_x: int) -> int:
        if local_x <= 0 or not self._text:
            return 0
        best = 0
        for i in range(len(self._text) + 1):
            w = self._text_pixel_width(self._text[:i])
            if w <= local_x:
                best = i
            else:
                break
        return best

    # -- line-edit helpers (Emacs / readline) ---------------------------------

    @staticmethod
    def _is_word_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    def _word_left(self, pos: int) -> int:
        """Index of the start of the word at/before ``pos`` (readline M-b)."""
        i = max(0, min(pos, len(self._text)))
        # Skip separators left of the caret.
        while i > 0 and not self._is_word_char(self._text[i - 1]):
            i -= 1
        while i > 0 and self._is_word_char(self._text[i - 1]):
            i -= 1
        return i

    def _word_right(self, pos: int) -> int:
        """Index past the end of the word at/after ``pos`` (readline M-f)."""
        n = len(self._text)
        i = max(0, min(pos, n))
        while i < n and not self._is_word_char(self._text[i]):
            i += 1
        while i < n and self._is_word_char(self._text[i]):
            i += 1
        return i

    def _delete_range(self, start: int, end: int, *, kill: bool) -> None:
        """Remove ``text[start:end]``; if ``kill``, store it for Ctrl+Y."""
        start = max(0, min(start, len(self._text)))
        end = max(start, min(end, len(self._text)))
        if start == end:
            return
        chunk = self._text[start:end]
        if kill:
            self._kill_buffer = chunk
        self._text = self._text[:start] + self._text[end:]
        self.cursor = start
        self._nudge_caret()
        self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)

    def _insert_text(self, s: str, screen_size: ScreenSize) -> bool:
        """Insert ``s`` at the caret if it fits. Return True if anything inserted."""
        if not s:
            return False
        candidate = self._text[: self.cursor] + s + self._text[self.cursor :]
        if not self._fits(candidate, screen_size):
            # Insert as many prefix chars as fit (yank may be long).
            kept = ""
            for ch in s:
                trial = self._text[: self.cursor] + kept + ch + self._text[self.cursor :]
                if not self._fits(trial, screen_size):
                    break
                kept += ch
            if not kept:
                return False
            s = kept
            candidate = self._text[: self.cursor] + s + self._text[self.cursor :]
        self._text = candidate
        self.cursor += len(s)
        self._nudge_caret()
        self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)
        return True

    def handle_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        """Handle a ``KEYDOWN`` while focused. Return True if consumed.

        Auto-repeat is not implemented inside the widget: when
        :func:`pygame.key.set_repeat` is enabled (see :class:`~magnetar.app.MagnetarApp`),
        the OS/SDL posts additional ``KEYDOWN`` events for a held key, and each is
        handled here the same as a fresh press.

        Bindings are named :class:`KeyEvent` entries (e.g. ``KeyEvent["HOME"]``).
        See the class docstring for the Emacs/readline map.
        """
        if not self.focused or not self.enabled or not self.visible:
            return False
        if event.type != pygame.KEYDOWN:
            return False

        mods = int(getattr(event, "mod", 0) or 0)
        chord = bool(mods & KeyEvent._CHORD_MODS)

        # --- movement --------------------------------------------------------
        if KeyEvent["BACKWARD_CHAR"].match(event):
            if self.cursor > 0:
                self.cursor -= 1
                self._nudge_caret()
            return True
        if KeyEvent["FORWARD_CHAR"].match(event):
            if self.cursor < len(self._text):
                self.cursor += 1
                self._nudge_caret()
            return True
        if KeyEvent["BACKWARD_WORD"].match(event):
            self.cursor = self._word_left(self.cursor)
            self._nudge_caret()
            return True
        if KeyEvent["FORWARD_WORD"].match(event):
            self.cursor = self._word_right(self.cursor)
            self._nudge_caret()
            return True
        if KeyEvent["HOME"].match(event):
            self.cursor = 0
            self._nudge_caret()
            return True
        if KeyEvent["END"].match(event):
            self.cursor = len(self._text)
            self._nudge_caret()
            return True

        # --- deletion / kill / yank ------------------------------------------
        if KeyEvent["KILL_WORD_BACKWARD"].match(event):
            start = self._word_left(self.cursor)
            self._delete_range(start, self.cursor, kill=True)
            return True
        if KeyEvent["BACKSPACE"].match(event):
            if self.cursor > 0:
                self._delete_range(self.cursor - 1, self.cursor, kill=False)
            return True
        if KeyEvent["DELETE_CHAR"].match(event):
            if self.cursor < len(self._text):
                self._delete_range(self.cursor, self.cursor + 1, kill=False)
            return True
        if KeyEvent["KILL_TO_END"].match(event):
            self._delete_range(self.cursor, len(self._text), kill=True)
            return True
        if KeyEvent["KILL_TO_START"].match(event):
            self._delete_range(0, self.cursor, kill=True)
            return True
        if KeyEvent["KILL_WORD_FORWARD"].match(event):
            end = self._word_right(self.cursor)
            self._delete_range(self.cursor, end, kill=True)
            return True
        if KeyEvent["YANK"].match(event):
            self._insert_text(self._kill_buffer, screen_size)
            return True
        if KeyEvent["COPY"].match(event):
            # Whole field for now; later: copy selection when present.
            try:
                set_text(self._text)
            except ClipboardError as exc:
                warnings.warn(
                    f"TextEntry COPY failed (clipboard set): {exc}",
                    stacklevel=2,
                )
            return True
        if KeyEvent["PASTE"].match(event):
            try:
                clip = get_text()
            except ClipboardError as exc:
                warnings.warn(
                    f"TextEntry PASTE failed (clipboard get): {exc}",
                    stacklevel=2,
                )
                clip = ""
            # Single-line field: drop newlines from multi-line pastes.
            clip = clip.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
            self._insert_text(clip, screen_size)
            return True
        if KeyEvent["TRANSPOSE"].match(event):
            # Swap char before caret with char at caret; at EOL swap last two.
            n = len(self._text)
            if n >= 2:
                if self.cursor == 0:
                    pass
                elif self.cursor == n:
                    a, b = self._text[n - 2], self._text[n - 1]
                    self._text = self._text[: n - 2] + b + a
                    self.cursor = n
                    self._nudge_caret()
                    self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)
                else:
                    a, b = self._text[self.cursor - 1], self._text[self.cursor]
                    self._text = (
                        self._text[: self.cursor - 1] + b + a + self._text[self.cursor + 1 :]
                    )
                    self.cursor += 1
                    self._nudge_caret()
                    self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)
            return True

        if KeyEvent["SUBMIT"].match(event):
            self.post_event(WIDGET_SUBMIT, text=self._text, cursor=self.cursor)
            self.invoke_command(self._text)
            return True
        if KeyEvent["BLUR"].match(event):
            self.blur()
            return True

        # Printable insert — ignore when a modifier chord is held.
        if chord:
            return False

        ch = getattr(event, "unicode", "") or ""
        if ch and ch.isprintable() and ch not in "\r\n\t":
            self._insert_text(ch, screen_size)
            return True

        # Consume un-modified keys while focused so global bindings (e.g. bare ``q``)
        # do not fire; leave unknown Ctrl/Alt/Meta combos to the app.
        if chord:
            return False
        key = event.key
        if key in (
            pygame.K_LSHIFT,
            pygame.K_RSHIFT,
            pygame.K_LCTRL,
            pygame.K_RCTRL,
            pygame.K_LALT,
            pygame.K_RALT,
            pygame.K_LMETA,
            pygame.K_RMETA,
            pygame.K_LGUI,
            pygame.K_RGUI,
        ):
            return False
        return True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WidgetRegistry:
    """Owns widgets and dispatches pygame mouse / key events to them."""

    def __init__(self) -> None:
        self._widgets: list[Widget] = []
        self._capture: Widget | None = None  # drag capture
        self._down_widget: Widget | None = None
        self._down_pos: Point | None = None
        self._focus: Widget | None = None

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
        if self._focus is widget:
            self._focus = None

    def clear(self) -> None:
        self._widgets.clear()
        self._capture = None
        self._down_widget = None
        self._focus = None

    def __iter__(self) -> Iterable[Widget]:
        return iter(self._widgets)

    @property
    def focus(self) -> Widget | None:
        return self._focus

    def set_focus(self, widget: Widget | None) -> None:
        """Update keyboard focus; blur a previous :class:`TextEntry` if needed."""
        if widget is self._focus:
            return
        prev = self._focus
        self._focus = widget
        if isinstance(prev, TextEntry) and prev.focused:
            prev.blur()
        if isinstance(widget, TextEntry) and not widget.focused:
            widget.focus()

    def clear_focus(self) -> None:
        self.set_focus(None)

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
            # Always consider downs so click-outside can clear focus.
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return (
                bool(mask & (EventInterest.CLICK | EventInterest.DRAG)) or self._capture is not None
            )
        if event.type == pygame.MOUSEMOTION:
            if event.buttons[0] and (mask & EventInterest.DRAG or self._capture is not None):
                return True
            return bool(mask & EventInterest.MOVE)
        if event.type == pygame.KEYDOWN:
            return self._focus is not None and bool(
                getattr(self._focus, "interest", EventInterest.NONE) & EventInterest.KEY
            )
        return False

    def widget_at(self, pos: Point, screen_size: ScreenSize) -> Widget | None:
        # Topmost = last added
        for widget in reversed(self._widgets):
            if widget.hit_test(pos, screen_size):
                return widget
        return None

    def dispatch(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        """Dispatch one pygame event. Returns True if a widget consumed it."""
        if event.type == pygame.KEYDOWN:
            return self._dispatch_key(event, screen_size)

        if not self.wants_event(event):
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            widget = self.widget_at(pos, screen_size)
            if widget is None:
                self.clear_focus()
                return False
            self._down_widget = widget
            self._down_pos = pos
            if widget.interest & EventInterest.DRAG:
                self._capture = widget
            if widget.interest & EventInterest.KEY:
                self.set_focus(widget)
            elif self._focus is not None and widget is not self._focus:
                self.clear_focus()
            pe = WidgetPointerEvent(kind="down", pos=pos, button=1, buttons=1)
            return widget.on_event(pe, screen_size)

        if event.type == pygame.MOUSEMOTION:
            pos = event.pos
            rel = event.rel
            buttons = 1 if event.buttons[0] else 0
            if self._capture is not None and event.buttons[0]:
                pe = WidgetPointerEvent(kind="drag", pos=pos, rel=rel, buttons=buttons, button=1)
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
            pe_up = WidgetPointerEvent(kind="up", pos=pos, button=1, buttons=0)
            target.on_event(pe_up, screen_size)
            if down_widget is target and down_pos is not None:
                pe_click = WidgetPointerEvent(kind="click", pos=pos, button=1, buttons=0)
                return target.on_event(pe_click, screen_size)
            return True

        return False

    def _dispatch_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        focus = self._focus
        if focus is None or not (focus.interest & EventInterest.KEY):
            return False
        consumed = focus.handle_key(event, screen_size)
        # TextEntry may blur itself (e.g. Esc); drop registry focus to match.
        if isinstance(focus, TextEntry) and not focus.focused and self._focus is focus:
            self._focus = None
        return consumed

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
