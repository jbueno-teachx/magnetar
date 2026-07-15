# SPDX-License-Identifier: CC0-1.0
"""Read-only multi-line text panel widget."""

from __future__ import annotations

import os
from typing import Iterable

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


class TextPanel(Widget):
    """Bordered, read-only multi-line text display.

    Placement uses the same percent + :class:`~magnetar.widgets.base.Anchor`
    model as other widgets. Content is a list of lines (character-cell grid):

    - :meth:`set_lines` / :meth:`set_text` replace content
    - :meth:`append_line` / :meth:`append_text` grow the buffer
    - :meth:`write` places text at ``(row, column)`` (0-based) on the grid
    - :meth:`clear` empties the buffer

    Drawing clips to the panel height. When :attr:`scroll_to_end` is true and
    more lines exist than fit, the **last** lines are shown (log-style).

    Optional close control
    ----------------------
    With ``closable=True``, an ``X`` is drawn in the upper-right border corner.
    Only that hit target receives clicks (the rest of the panel is pass-through).
    Activating it sets :attr:`visible` to ``False`` and invokes ``on_close``.
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
        lines: list[str] | None = None,
        text: str = "",
        name: str = "",
        command: Command = None,
        fill: tuple[int, int, int, int] | None = (8, 16, 20, 200),
        border: tuple[int, int, int] | None = (0, 255, 255),
        text_color: tuple[int, int, int] = (0, 255, 255),
        padding_px: int = 8,
        line_gap_px: int = 2,
        scroll_to_end: bool = False,
        max_lines: int | None = 200,
        closable: bool = False,
        on_close: Command = None,
        close_size_px: int = 18,
        close_color: tuple[int, int, int] | None = None,
    ) -> None:
        interest = EventInterest.CLICK if closable else EventInterest.NONE
        super().__init__(
            x_pct,
            y_pct,
            w_pct,
            h_pct,
            anchor=anchor,
            command=command,
            name=name or "textpanel",
            interest=interest,
            enabled=True,
        )
        self.font = font
        self.fill = fill
        self.border = border
        self.text_color = text_color
        self.padding_px = int(padding_px)
        self.line_gap_px = int(line_gap_px)
        self.scroll_to_end = bool(scroll_to_end)
        self.max_lines = max_lines
        self.closable = bool(closable)
        self.on_close = on_close
        self.close_size_px = max(10, int(close_size_px))
        self.close_color = close_color
        self._lines: list[str] = []
        if lines is not None:
            self.set_lines(lines)
        elif text:
            self.set_text(text)

    # -- content API ----------------------------------------------------------

    @property
    def lines(self) -> list[str]:
        """Copy of the current line buffer."""
        return list(self._lines)

    def clear(self) -> None:
        self._lines.clear()

    def set_lines(self, lines: list[str] | tuple[str, ...] | Iterable[str]) -> None:
        """Replace all content with ``lines`` (each item one row)."""
        self._lines = [str(line).replace("\r\n", "\n").replace("\r", "\n") for line in lines]
        flat: list[str] = []
        for line in self._lines:
            flat.extend(line.split("\n"))
        self._lines = flat
        self._trim()

    def set_text(self, text: str) -> None:
        """Replace content from a single string (split on newlines)."""
        self.set_lines(str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"))

    def append_line(self, line: str = "") -> None:
        """Append one logical line (embedded newlines become extra rows)."""
        for part in str(line).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            self._lines.append(part)
        self._trim()

    def append_text(self, text: str) -> None:
        """Append multi-line text (same as successive :meth:`append_line`)."""
        self.append_line(text)

    def write(self, row: int, col: int, text: str) -> None:
        """Place ``text`` starting at grid cell ``(row, col)`` (0-based).

        Expands the buffer with blank lines / spaces as needed. If ``text``
        contains newlines, subsequent segments continue on the next rows at
        column 0.
        """
        if row < 0 or col < 0:
            raise ValueError(f"row and col must be >= 0 (got row={row}, col={col})")
        parts = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, part in enumerate(parts):
            r = row + i
            c = col if i == 0 else 0
            while len(self._lines) <= r:
                self._lines.append("")
            line = self._lines[r]
            if len(line) < c:
                line = line + (" " * (c - len(line)))
            end = c + len(part)
            if len(line) < end:
                line = line + (" " * (end - len(line)))
            self._lines[r] = line[:c] + part + line[end:]
        self._trim()

    def _trim(self) -> None:
        if self.max_lines is not None and self.max_lines > 0 and len(self._lines) > self.max_lines:
            self._lines = self._lines[-int(self.max_lines) :]

    def show(self) -> None:
        """Make the panel visible again (e.g. after close when new output arrives)."""
        self.visible = True

    def hide(self) -> None:
        """Hide the panel (same as the close-button action without the callback)."""
        self.visible = False

    # -- close control --------------------------------------------------------

    def close_rect(self, screen_size: ScreenSize) -> pygame.Rect:
        """Pixel rect of the upper-right ``X`` hit target (inside the border)."""
        rect = self.screen_rect(screen_size)
        size = min(self.close_size_px, max(10, rect.width // 4), max(10, rect.height // 2))
        # Inset slightly so the X sits on the border corner, not outside.
        inset = 2
        return pygame.Rect(
            rect.right - size - inset,
            rect.top + inset,
            size,
            size,
        )

    def hit_test(self, pos: Point, screen_size: ScreenSize) -> bool:
        """Pointer hits: only the close ``X`` when closable; otherwise pass-through."""
        if not self.visible or not self.enabled:
            return False
        if self.closable:
            return self.close_rect(screen_size).collidepoint(pos)
        return False

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        if not self.closable or not self.visible:
            return False
        if event.kind in ("click", "down") and event.button == 1:
            if self.close_rect(screen_size).collidepoint(event.pos):
                if event.kind == "click":
                    self.hide()
                    if self.on_close is not None:
                        self.on_close()
                return True
        return False

    # -- layout helpers -------------------------------------------------------

    def line_height(self) -> int:
        if self.font is None:
            return 16 + self.line_gap_px
        return self.font.get_height() + self.line_gap_px

    def _text_padding_right(self, screen_size: ScreenSize) -> int:
        """Reserve space on the right so text does not draw under the close X."""
        if not self.closable:
            return self.padding_px
        cr = self.close_rect(screen_size)
        return max(self.padding_px, cr.width + 6)

    def visible_line_capacity(self, screen_size: ScreenSize) -> int:
        """How many text rows fit inside the padded panel."""
        rect = self.screen_rect(screen_size)
        # When closable, top padding accounts for the close control height.
        top_pad = self.padding_px
        if self.closable:
            top_pad = max(top_pad, self.close_rect(screen_size).height + 2)
        inner_h = max(0, rect.height - top_pad - self.padding_px)
        lh = max(1, self.line_height())
        return max(0, inner_h // lh)

    def _visible_slice(self, screen_size: ScreenSize) -> list[str]:
        cap = self.visible_line_capacity(screen_size)
        if cap <= 0 or not self._lines:
            return []
        if len(self._lines) <= cap:
            return self._lines
        if self.scroll_to_end:
            return self._lines[-cap:]
        return self._lines[:cap]

    def _draw_close_x(self, surface: pygame.Surface, screen_size: ScreenSize) -> None:
        cr = self.close_rect(screen_size)
        color = self.close_color
        if color is None:
            color = self.border if self.border is not None else self.text_color
        # Subtle corner plate so the X reads as part of the chrome.
        plate = pygame.Surface(cr.size, pygame.SRCALPHA)
        plate.fill((0, 0, 0, 120))
        surface.blit(plate, cr.topleft)
        pad = max(3, cr.width // 4)
        x0, y0 = cr.left + pad, cr.top + pad
        x1, y1 = cr.right - pad - 1, cr.bottom - pad - 1
        pygame.draw.line(surface, color, (x0, y0), (x1, y1), 2)
        pygame.draw.line(surface, color, (x1, y0), (x0, y1), 2)

    # -- drawing --------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        rect = self.screen_rect(surface.get_size())
        screen_size = surface.get_size()
        if self.fill is not None:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(self.fill)
            surface.blit(overlay, rect.topleft)
        if self.border is not None:
            pygame.draw.rect(surface, self.border, rect, width=1, border_radius=3)

        if self.closable:
            self._draw_close_x(surface, screen_size)

        if self.font is None:
            return

        visible = self._visible_slice(screen_size)
        if not visible:
            return

        top_pad = self.padding_px
        if self.closable:
            top_pad = max(top_pad, self.close_rect(screen_size).height + 2)
        x0 = rect.x + self.padding_px
        y = rect.y + top_pad
        max_w = max(0, rect.width - self.padding_px - self._text_padding_right(screen_size))
        lh = self.line_height()
        bottom = rect.bottom - self.padding_px

        for line in visible:
            if y + self.font.get_height() > bottom:
                break
            shown = line
            if max_w > 0 and self.font.size(shown)[0] > max_w:
                lo, hi = 0, len(shown)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if self.font.size(shown[:mid])[0] <= max_w:
                        lo = mid
                    else:
                        hi = mid - 1
                shown = shown[:lo]
                if lo > 1 and self.font.size(shown[:-1] + "…")[0] <= max_w:
                    shown = shown[:-1] + "…"
            if shown:
                img = self.font.render(shown, True, self.text_color)
                surface.blit(img, (x0, y))
            y += lh
