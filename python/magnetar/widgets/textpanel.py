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
    WidgetPointerEvent,
)
from magnetar.widgets.textbase import TextWidget
from magnetar.widgets.theme import theme_value


class TextPanel(TextWidget):
    """Bordered, read-only multi-line text display.

    Placement uses the same percent + :class:`~magnetar.widgets.base.Anchor`
    model as other widgets. Content is a list of lines (character-cell grid):

    - :meth:`set_lines` / :meth:`set_text` replace content
    - :meth:`append_line` / :meth:`append_text` grow the buffer
    - :meth:`write` places text at ``(row, column)`` (0-based) on the grid
    - :meth:`clear` empties the buffer

    Equal content assignments are no-ops and do **not** raise the dirty flag
    (see :class:`~magnetar.widgets.textbase.TextWidget`).

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
        color: tuple[int, int, int] | None = None,
        background: tuple[int, int, int, int] | None = None,
        border: tuple[int, int, int] | None = None,
        padding: int | None = None,
        line_gap: int | None = None,
        scroll_to_end: bool = False,
        max_lines: int | None = 200,
        closable: bool = False,
        on_close: Command = None,
        close_size_px: int = 18,
        close_color: tuple[int, int, int] | None = None,
        # Back-compat aliases
        fill: tuple[int, int, int, int] | None = None,
        text_color: tuple[int, int, int] | None = None,
        padding_px: int | None = None,
        line_gap_px: int | None = None,
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
            font=font,
            color=color if color is not None else text_color,
            background=background if background is not None else fill,
            border=border,
            padding=padding if padding is not None else padding_px,
        )
        self.line_gap = line_gap if line_gap is not None else line_gap_px
        self.scroll_to_end = bool(scroll_to_end)
        self.max_lines = max_lines
        self.closable = bool(closable)
        self.on_close = on_close
        self.close_size_px = max(10, int(close_size_px))
        self.close_color = close_color
        # Multi-line content key starts empty.
        self._content_key = ()
        self._dirty = False
        if lines is not None:
            self.set_lines(lines)
        elif text:
            self.set_text(text)

    # -- content API ----------------------------------------------------------

    @property
    def lines(self) -> list[str]:
        """Copy of the current line buffer."""
        key = self._content_key
        if isinstance(key, tuple):
            return list(key)
        return []

    def _apply_max(self, rows: list[str]) -> list[str]:
        if self.max_lines is not None and self.max_lines > 0 and len(rows) > self.max_lines:
            return rows[-int(self.max_lines) :]
        return rows

    @staticmethod
    def _flatten(lines: Iterable[str]) -> list[str]:
        flat: list[str] = []
        for line in lines:
            for part in str(line).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                flat.append(part)
        return flat

    def clear(self) -> None:
        self.commit_lines(())

    def set_lines(self, lines: list[str] | tuple[str, ...] | Iterable[str]) -> bool:
        """Replace all content with ``lines``. Return True if content changed."""
        flat = self._apply_max(self._flatten(lines))
        return self.commit_lines(flat)

    def set_text(self, text: str) -> bool:
        """Replace content from a single string (split on newlines)."""
        return self.set_lines(str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"))

    def append_line(self, line: str = "") -> bool:
        """Append one logical line. Return True if content changed."""
        rows = self.lines
        for part in str(line).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            rows.append(part)
        return self.commit_lines(self._apply_max(rows))

    def append_text(self, text: str) -> bool:
        """Append multi-line text (same as successive :meth:`append_line`)."""
        return self.append_line(text)

    def write(self, row: int, col: int, text: str) -> bool:
        """Place ``text`` starting at grid cell ``(row, col)`` (0-based).

        Expands the buffer with blank lines / spaces as needed. If ``text``
        contains newlines, subsequent segments continue on the next rows at
        column 0. Return True if content changed.
        """
        if row < 0 or col < 0:
            raise ValueError(f"row and col must be >= 0 (got row={row}, col={col})")
        rows = self.lines
        parts = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, part in enumerate(parts):
            r = row + i
            c = col if i == 0 else 0
            while len(rows) <= r:
                rows.append("")
            line = rows[r]
            if len(line) < c:
                line = line + (" " * (c - len(line)))
            end = c + len(part)
            if len(line) < end:
                line = line + (" " * (end - len(line)))
            rows[r] = line[:c] + part + line[end:]
        return self.commit_lines(self._apply_max(rows))

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
        gap = int(theme_value("line_gap", self.line_gap, 2))
        font = self.theme_font()
        if font is None:
            return 16 + gap
        return font.get_height() + gap

    def _text_padding_right(self, screen_size: ScreenSize) -> int:
        """Reserve space on the right so text does not draw under the close X."""
        pad = self.theme_padding()
        if not self.closable:
            return pad
        cr = self.close_rect(screen_size)
        return max(pad, cr.width + 6)

    def visible_line_capacity(self, screen_size: ScreenSize) -> int:
        """How many text rows fit inside the padded panel."""
        rect = self.screen_rect(screen_size)
        pad = self.theme_padding()
        top_pad = pad
        if self.closable:
            top_pad = max(top_pad, self.close_rect(screen_size).height + 2)
        inner_h = max(0, rect.height - top_pad - pad)
        lh = max(1, self.line_height())
        return max(0, inner_h // lh)

    def _visible_slice(self, screen_size: ScreenSize) -> list[str]:
        rows = self.lines
        cap = self.visible_line_capacity(screen_size)
        if cap <= 0 or not rows:
            return []
        if len(rows) <= cap:
            return rows
        if self.scroll_to_end:
            return rows[-cap:]
        return rows[:cap]

    def _draw_close_x(self, surface: pygame.Surface, screen_size: ScreenSize) -> None:
        cr = self.close_rect(screen_size)
        color = self.close_color
        if color is None:
            color = self.theme_border() or self.theme_color()
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
        fill = self.theme_background(key="background")
        if fill is not None:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(fill)
            surface.blit(overlay, rect.topleft)
        border = self.theme_border()
        if border is not None:
            pygame.draw.rect(
                surface,
                border,
                rect,
                width=self.theme_border_width(),
                border_radius=self.theme_border_radius(),
            )

        if self.closable:
            self._draw_close_x(surface, screen_size)

        font = self.theme_font()
        if font is None:
            return

        visible = self._visible_slice(screen_size)
        if not visible:
            return

        pad = self.theme_padding()
        top_pad = pad
        if self.closable:
            top_pad = max(top_pad, self.close_rect(screen_size).height + 2)
        x0 = rect.x + pad
        y = rect.y + top_pad
        max_w = max(0, rect.width - pad - self._text_padding_right(screen_size))
        lh = self.line_height()
        bottom = rect.bottom - pad
        color = self.theme_color()

        for line in visible:
            if y + font.get_height() > bottom:
                break
            shown = line
            if max_w > 0 and font.size(shown)[0] > max_w:
                lo, hi = 0, len(shown)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if font.size(shown[:mid])[0] <= max_w:
                        lo = mid
                    else:
                        hi = mid - 1
                shown = shown[:lo]
                if lo > 1 and font.size(shown[:-1] + "…")[0] <= max_w:
                    shown = shown[:-1] + "…"
            if shown:
                img = font.render(shown, True, color)
                surface.blit(img, (x0, y))
            y += lh
