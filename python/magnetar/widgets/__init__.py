# SPDX-License-Identifier: CC0-1.0
"""In-window UI widgets package.

Public lifecycle (mirrors pygame style)::

    magnetar.widgets.init()   # start clipboard Tk server (after pygame init)
    magnetar.widgets.quit()   # stop clipboard Tk server (before pygame.quit)
"""

from __future__ import annotations

import warnings

from magnetar.widgets.base import (
    Anchor,
    AnchorH,
    AnchorV,
    AnchorLike,
    Command,
    EventInterest,
    Point,
    ScreenSize,
    WIDGET_BLUR,
    WIDGET_CHANGED,
    WIDGET_FOCUS,
    WIDGET_SUBMIT,
    Widget,
    WidgetPointerEvent,
)
from magnetar.widgets.buttons import Button, DragImageButton, make_curved_arrows_icon
from magnetar.widgets.history_textentry import HistoryTextEntry
from magnetar.widgets.keyevent import KeyEvent
from magnetar.widgets.registry import WidgetRegistry
from magnetar.widgets.textbase import TextWidget
from magnetar.widgets.textentry import TextEntry
from magnetar.widgets.textpanel import TextPanel

__all__ = [
    "Anchor",
    "AnchorH",
    "AnchorV",
    "AnchorLike",
    "Button",
    "Command",
    "DragImageButton",
    "EventInterest",
    "HistoryTextEntry",
    "KeyEvent",
    "Point",
    "ScreenSize",
    "TextEntry",
    "TextPanel",
    "TextWidget",
    "WIDGET_BLUR",
    "WIDGET_CHANGED",
    "WIDGET_FOCUS",
    "WIDGET_SUBMIT",
    "Widget",
    "WidgetPointerEvent",
    "WidgetRegistry",
    "init",
    "make_curved_arrows_icon",
    "quit",
]


def init() -> None:
    """Start widget subsystem services (clipboard Tk mainloop thread).

    Safe to call more than once. If tkinter / display is unavailable, logs a
    :class:`UserWarning` and continues (copy/paste will warn on use).
    """
    try:
        from magnetar.widgets import clipboard as _clip

        _clip.available()  # starts worker or raises ClipboardError
    except Exception as exc:  # noqa: BLE001 — optional service
        warnings.warn(
            f"magnetar.widgets.init: clipboard unavailable ({exc})",
            stacklevel=2,
        )


def quit() -> None:
    """Stop widget subsystem services (history flush + clipboard Tk thread)."""
    try:
        from magnetar.widgets.history import save_all_histories

        save_all_histories()
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"magnetar.widgets.quit: history save failed ({exc})",
            stacklevel=2,
        )
    try:
        from magnetar.widgets import clipboard as _clip

        _clip.shutdown()
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"magnetar.widgets.quit: clipboard shutdown failed ({exc})",
            stacklevel=2,
        )
