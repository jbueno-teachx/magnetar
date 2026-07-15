# SPDX-License-Identifier: CC0-1.0
"""Widget registry: focus, mouse/key dispatch, drawing."""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.widgets.base import EventInterest, Point, ScreenSize, Widget, WidgetPointerEvent
from magnetar.widgets.textentry import TextEntry

# Optional: (bucket_name, seconds) → used when app enables UI profiling.
ProfileSink = Callable[[str, float], None]


class WidgetRegistry:
    """Owns widgets and dispatches pygame mouse / key events to them."""

    def __init__(self) -> None:
        self._widgets: list[Widget] = []
        self._capture: Widget | None = None  # drag capture
        self._down_widget: Widget | None = None
        self._down_pos: Point | None = None
        self._focus: Widget | None = None
        # When set, :meth:`draw` reports per-widget times as ``widget.<name>``.
        self.profile_sink: ProfileSink | None = None

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
        sink = self.profile_sink
        for widget in self._widgets:
            if not widget.visible:
                continue
            if sink is None:
                widget.draw(surface)
                continue
            t0 = time.perf_counter()
            widget.draw(surface)
            sink(f"widget.{widget.name}", time.perf_counter() - t0)
