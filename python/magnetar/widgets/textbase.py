# SPDX-License-Identifier: CC0-1.0
"""Shared base for text-bearing widgets (:class:`TextEntry`, :class:`TextPanel`)."""

from __future__ import annotations

import os
from typing import Sequence

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.widgets.base import (
    AnchorLike,
    Command,
    EventInterest,
    Widget,
)
from magnetar.widgets.theme import theme_value


class TextWidget(Widget):
    """Widget that owns textual content and a paint **dirty** flag.

    Subclasses keep a canonical content snapshot (string or lines). Mutators
    should call :meth:`commit_text` / :meth:`commit_lines` so that assigning
    *equal* content is a no-op and does **not** set ``_dirty``.

    Style attributes (``color``, ``background``, ``border``, ``padding``,
    ``font``) use CSS-inspired names. ``None`` means “take from the active
    theme” via :func:`~magnetar.widgets.theme.theme_value` at draw/layout time
    so a theme object can later animate with ``@property``.
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
        interest: EventInterest = EventInterest.NONE,
        visible: bool = True,
        enabled: bool = True,
        font: pygame.font.Font | None = None,
        color: tuple[int, int, int] | None = None,
        background: tuple[int, int, int, int] | None = None,
        border: tuple[int, int, int] | None = None,
        padding: int | None = None,
        # Back-compat aliases (prefer CSS names above).
        text_color: tuple[int, int, int] | None = None,
        fill: tuple[int, int, int, int] | None = None,
        padding_px: int | None = None,
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
            visible=visible,
            enabled=enabled,
        )
        # Per-widget overrides; None → active theme.
        self.font = font
        self.color = color if color is not None else text_color
        self.background = background if background is not None else fill
        self.border = border
        self.padding = padding if padding is not None else padding_px
        self._dirty: bool = True
        # Canonical content fingerprint for equality short-circuit.
        # TextEntry: str; TextPanel: tuple[str, ...].
        self._content_key: str | tuple[str, ...] = ""

    # -- theme resolution (no getters — call these where values are needed) ---

    def theme_color(self) -> tuple[int, int, int]:
        return theme_value("color", self.color, (0, 255, 255))

    def theme_background(self, *, key: str = "background") -> tuple[int, int, int, int] | None:
        """Resolve panel fill. ``key`` selects theme attr when override is None."""
        if self.background is not None:
            return self.background
        return theme_value(key, None, None)

    def theme_border(self) -> tuple[int, int, int] | None:
        return theme_value("border", self.border, None)

    def theme_padding(self) -> int:
        return int(theme_value("padding", self.padding, 8))

    def theme_font(self) -> pygame.font.Font | None:
        if self.font is not None:
            return self.font
        return theme_value("font", None, None)

    def theme_border_width(self) -> int:
        return int(theme_value("border_width", None, 1))

    def theme_border_radius(self) -> int:
        return int(theme_value("border_radius", None, 3))

    def set_font(self, font: pygame.font.Font | None) -> None:
        if font is self.font:
            return
        self.font = font
        self._dirty = True

    def commit_text(self, text: str) -> bool:
        """Set single-string content. Return True if it actually changed."""
        key = str(text)
        if key == self._content_key:
            return False
        self._content_key = key
        self._dirty = True
        return True

    def commit_lines(self, lines: Sequence[str]) -> bool:
        """Set multi-line content. Return True if it actually changed."""
        key = tuple(str(line) for line in lines)
        if key == self._content_key:
            return False
        self._content_key = key
        self._dirty = True
        return True

    def clear_content(self) -> bool:
        """Empty content. Return True if something was cleared."""
        if self._content_key == "" or self._content_key == ():
            return False
        if isinstance(self._content_key, tuple):
            self._content_key = ()
        else:
            self._content_key = ""
        self._dirty = True
        return True
