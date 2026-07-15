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


class TextWidget(Widget):
    """Widget that owns textual content and a paint **dirty** flag.

    Subclasses keep a canonical content snapshot (string or lines). Mutators
    should call :meth:`commit_text` / :meth:`commit_lines` so that assigning
    *equal* content is a no-op and does **not** set the dirty flag.

    ``_dirty`` means rasterized text may be stale (for future surface / glyph
    caches). The screen is still fully cleared each frame by the app, so
    :meth:`draw` still runs every frame; ``_dirty`` only gates *rebuilding*
    cached glyphs when a cache exists. Use the attribute directly inside this
    package — no getter/setter wrappers.
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
        fill: tuple[int, int, int, int] | None = None,
        border: tuple[int, int, int] | None = None,
        text_color: tuple[int, int, int] = (0, 255, 255),
        padding_px: int = 8,
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
        self.font = font
        self.fill = fill
        self.border = border
        self.text_color = text_color
        self.padding_px = int(padding_px)
        # Paint/content invalidation for glyph/surface caches (widgets package only).
        self._dirty: bool = True
        # Canonical content fingerprint for equality short-circuit.
        # TextEntry: str; TextPanel: tuple[str, ...].
        self._content_key: str | tuple[str, ...] = ""

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
        # Prefer empty string for single-line widgets; panels use empty tuple.
        if isinstance(self._content_key, tuple):
            self._content_key = ()
        else:
            self._content_key = ""
        self._dirty = True
        return True