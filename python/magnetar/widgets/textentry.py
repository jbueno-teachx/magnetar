# SPDX-License-Identifier: CC0-1.0
"""Single-line text entry widget with selection."""

from __future__ import annotations

import os
import warnings

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.widgets.base import (
    AnchorLike,
    Command,
    EventInterest,
    ScreenSize,
    WIDGET_BLUR,
    WIDGET_CHANGED,
    WIDGET_FOCUS,
    WIDGET_SUBMIT,
    WidgetPointerEvent,
)
from magnetar.widgets.clipboard import ClipboardError, get_text, set_text
from magnetar.widgets.keyevent import KeyEvent
from magnetar.widgets.textbase import TextWidget


class TextEntry(TextWidget):
    """Single-line text field with a ``|`` caret and optional selection.

    Keyboard handling runs only while :attr:`focused`. Length is limited so the
    rendered text fits the on-screen pixel width of the widget.

    Selection
    ---------
    - Click + drag highlights a range (reverse colors).
    - Shift + movement chords extend/shrink the selection.
    - Plain click places the caret and clears selection.
    - Typing / paste replaces the selection; Backspace/Delete remove only it.

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
        (+ Shift)         extend selection

    Deletion / kill (one-slot kill buffer for yank)::

        Ctrl+D / Delete   delete char under cursor (or selection)
        Ctrl+H / Backspace  delete char before cursor (or selection)
        Ctrl+K            kill to end of line
        Ctrl+U            kill to beginning of line
        Ctrl+W            kill word backward
        Alt+D             kill word forward
        Alt+Backspace     kill word backward
        Ctrl+Y            yank last kill (internal kill buffer)

    System clipboard::

        Ctrl+C / Ctrl+Shift+C / Cmd+C   copy selection (or all if none)
        Ctrl+X / Cmd+X                  cut selection (or all if none)
        Ctrl+V / Cmd+V / Shift+Insert   paste (replaces selection)

    Other::

        Ctrl+T            transpose characters around cursor
        Enter             submit (``WIDGET_SUBMIT``)
        Esc               blur
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
        selection_fg: tuple[int, int, int] | None = None,
        selection_bg: tuple[int, int, int] | None = None,
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
            interest=EventInterest.CLICK | EventInterest.KEY | EventInterest.DRAG,
            font=font,
            fill=fill,
            border=border,
            text_color=text_color,
            padding_px=padding_px,
        )
        self.commit_text(str(text))
        self.placeholder = placeholder
        self.border_focused = border_focused
        self.placeholder_color = placeholder_color
        self.caret_color = caret_color
        # Reverse video defaults: invert text/fill for selected span.
        self.selection_fg = selection_fg
        self.selection_bg = selection_bg
        self.caret_blink_ms = int(caret_blink_ms)
        self.focused = False
        self.cursor = len(self._text)
        self._caret_force_on_until: int = 0
        self._kill_buffer: str = ""
        # Fixed selection range ``(start, end)`` exclusive end — independent of
        # the caret so non-Shift movement can move the caret without clearing
        # the highlight. ``None`` means no selection.
        self._sel: tuple[int, int] | None = None
        self._drag_anchor: int | None = None
        self._mouse_selecting = False
        self._mouse_dragged = False

    # -- text / caret / selection ---------------------------------------------

    @property
    def _text(self) -> str:
        """Working buffer (backed by ``_content_key`` for equality / dirty)."""
        key = self._content_key
        return key if isinstance(key, str) else ""

    @_text.setter
    def _text(self, value: str) -> None:
        self.commit_text(str(value))

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        if not self.commit_text(str(value)):
            return
        n = len(self._text)
        self.cursor = min(self.cursor, n)
        if self._sel is not None:
            a, b = self._sel
            a, b = min(a, n), min(b, n)
            self._sel = (a, b) if a != b else None

    def has_selection(self) -> bool:
        return self._sel is not None and self._sel[0] != self._sel[1]

    def selection_range(self) -> tuple[int, int]:
        """Inclusive-start exclusive-end indices of the selection (or caret, caret)."""
        if not self.has_selection() or self._sel is None:
            return (self.cursor, self.cursor)
        a, b = self._sel
        return (min(a, b), max(a, b))

    def selected_text(self) -> str:
        a, b = self.selection_range()
        return self._text[a:b]

    def clear_selection(self) -> None:
        self._sel = None
        self._drag_anchor = None

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
        self.clear_selection()
        self._mouse_selecting = False
        self._mouse_dragged = False
        self.post_event(WIDGET_BLUR, text=self._text, cursor=self.cursor)

    def clear(self, *, notify: bool = True) -> None:
        if not self._text and self.cursor == 0:
            return
        changed = self.commit_text("")
        self.cursor = 0
        self.clear_selection()
        self._nudge_caret()
        if notify and changed:
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
        # Caret still blinks when selection exists (caret can move independently).
        now = pygame.time.get_ticks()
        if now < self._caret_force_on_until:
            return True
        period = max(1, self.caret_blink_ms)
        return (now // period) % 2 == 0

    def _sel_colors(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """Return ``(fg, bg)`` for selected text (reverse of normal)."""
        if self.selection_fg is not None and self.selection_bg is not None:
            return self.selection_fg, self.selection_bg
        bg = self.text_color
        if self.fill is not None and len(self.fill) >= 3:
            fg = (int(self.fill[0]), int(self.fill[1]), int(self.fill[2]))
        else:
            fg = (0, 0, 0)
        if self.selection_fg is not None:
            fg = self.selection_fg
        if self.selection_bg is not None:
            bg = self.selection_bg
        return fg, bg

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

        if self.has_selection():
            self._draw_with_selection(surface, inner_x, inner_y)
        else:
            self._draw_plain(surface, inner_x, inner_y)
        # Caret always at ``cursor`` (may sit outside a preserved selection).
        if self._caret_visible():
            caret_x = inner_x + self._text_pixel_width(self._text[: self.cursor])
            caret = self.font.render("|", True, self.caret_color)
            surface.blit(caret, (caret_x - caret.get_width() // 2, inner_y))

    def _draw_plain(self, surface: pygame.Surface, inner_x: int, inner_y: int) -> None:
        assert self.font is not None
        if self._text:
            img = self.font.render(self._text, True, self.text_color)
            surface.blit(img, (inner_x, inner_y))

    def _draw_with_selection(self, surface: pygame.Surface, inner_x: int, inner_y: int) -> None:
        assert self.font is not None
        a, b = self.selection_range()
        pre, mid, post = self._text[:a], self._text[a:b], self._text[b:]
        sel_fg, sel_bg = self._sel_colors()
        x = inner_x
        if pre:
            img = self.font.render(pre, True, self.text_color)
            surface.blit(img, (x, inner_y))
            x += img.get_width()
        if mid:
            img = self.font.render(mid, True, sel_fg)
            bar = pygame.Rect(x, inner_y, img.get_width(), self.font.get_height())
            pygame.draw.rect(surface, sel_bg, bar)
            surface.blit(img, (x, inner_y))
            x += img.get_width()
        if post:
            img = self.font.render(post, True, self.text_color)
            surface.blit(img, (x, inner_y))

    # -- pointer / keyboard ---------------------------------------------------

    def on_event(self, event: WidgetPointerEvent, screen_size: ScreenSize) -> bool:
        if event.kind == "down" and event.button == 1:
            self.focus()
            idx = self._index_at_pos(event.pos, screen_size)
            self._drag_anchor = idx
            self.cursor = idx
            # New press starts a potential selection; collapse until drag moves.
            self._sel = None
            self._mouse_selecting = True
            self._mouse_dragged = False
            self._nudge_caret()
            return True

        if event.kind == "drag" and self._mouse_selecting:
            idx = self._index_at_pos(event.pos, screen_size)
            if idx != self.cursor:
                self._mouse_dragged = True
            self.cursor = idx
            if self._drag_anchor is not None and idx != self._drag_anchor:
                a, b = self._drag_anchor, idx
                self._sel = (min(a, b), max(a, b))
            else:
                self._sel = None
            self._nudge_caret()
            return True

        if event.kind == "up" and event.button == 1:
            self._mouse_selecting = False
            if self._sel is not None and self._sel[0] == self._sel[1]:
                self.clear_selection()
            return True

        if event.kind == "click" and event.button == 1:
            # Pure click (no drag): place caret and clear selection.
            if not self._mouse_dragged:
                idx = self._index_at_pos(event.pos, screen_size)
                self.cursor = idx
                self.clear_selection()
                self._nudge_caret()
            self._mouse_dragged = False
            self._drag_anchor = None
            return True

        return False

    def _index_at_pos(self, pos: tuple[int, int], screen_size: ScreenSize) -> int:
        rect = self.screen_rect(screen_size)
        local_x = pos[0] - rect.x - self.padding_px
        return self._index_for_x(local_x)

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

    def _move_to(self, new_pos: int, *, extend: bool) -> None:
        new_pos = max(0, min(int(new_pos), len(self._text)))
        if extend:
            # Shift+move: grow/shrink selection; anchor is the stable end.
            if self._sel is None:
                anchor = self.cursor
            else:
                a, b = self.selection_range()
                # Keep the end that is not under the caret as the anchor.
                if self.cursor <= a:
                    anchor = b
                elif self.cursor >= b:
                    anchor = a
                else:
                    # Caret inside selection: extend from nearer edge.
                    anchor = a if abs(self.cursor - a) <= abs(self.cursor - b) else b
            self.cursor = new_pos
            if anchor == new_pos:
                self._sel = None
            else:
                self._sel = (min(anchor, new_pos), max(anchor, new_pos))
        else:
            # Non-selecting move: relocate caret only; keep existing highlight.
            self.cursor = new_pos
        self._nudge_caret()

    def _delete_selection(self, *, kill: bool = False) -> bool:
        """Delete the selected range. Return True if there was a selection."""
        if not self.has_selection():
            return False
        a, b = self.selection_range()
        self.clear_selection()
        self._delete_range(a, b, kill=kill)
        return True

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
        self.clear_selection()
        self._nudge_caret()
        self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)

    def _insert_text(self, s: str, screen_size: ScreenSize) -> bool:
        """Insert ``s`` at the caret (replacing selection) if it fits."""
        if self.has_selection():
            self._delete_selection(kill=False)
        if not s:
            return False
        candidate = self._text[: self.cursor] + s + self._text[self.cursor :]
        if not self._fits(candidate, screen_size):
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
        self.clear_selection()
        self._nudge_caret()
        self.post_event(WIDGET_CHANGED, text=self._text, cursor=self.cursor)
        return True

    def _clipboard_payload(self) -> str:
        """Text for copy/cut: selection if any, else the whole field."""
        if self.has_selection():
            return self.selected_text()
        return self._text

    def handle_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        """Handle a ``KEYDOWN`` while focused. Return True if consumed."""
        if not self.focused or not self.enabled or not self.visible:
            return False
        if event.type != pygame.KEYDOWN:
            return False

        mods = int(getattr(event, "mod", 0) or 0)
        chord = bool(mods & KeyEvent._CHORD_MODS)
        extend = bool(mods & pygame.KMOD_SHIFT)

        # --- movement (Shift extends selection) ------------------------------
        if KeyEvent["BACKWARD_CHAR"].match(event):
            self._move_to(self.cursor - 1, extend=extend)
            return True
        if KeyEvent["FORWARD_CHAR"].match(event):
            self._move_to(self.cursor + 1, extend=extend)
            return True
        if KeyEvent["BACKWARD_WORD"].match(event):
            self._move_to(self._word_left(self.cursor), extend=extend)
            return True
        if KeyEvent["FORWARD_WORD"].match(event):
            self._move_to(self._word_right(self.cursor), extend=extend)
            return True
        if KeyEvent["HOME"].match(event):
            self._move_to(0, extend=extend)
            return True
        if KeyEvent["END"].match(event):
            self._move_to(len(self._text), extend=extend)
            return True

        # --- deletion / kill / yank ------------------------------------------
        if KeyEvent["KILL_WORD_BACKWARD"].match(event):
            if self.has_selection():
                self._delete_selection(kill=True)
            else:
                start = self._word_left(self.cursor)
                self._delete_range(start, self.cursor, kill=True)
            return True
        if KeyEvent["BACKSPACE"].match(event):
            if self.has_selection():
                self._delete_selection(kill=False)
            elif self.cursor > 0:
                self._delete_range(self.cursor - 1, self.cursor, kill=False)
            return True
        if KeyEvent["DELETE_CHAR"].match(event):
            if self.has_selection():
                self._delete_selection(kill=False)
            elif self.cursor < len(self._text):
                self._delete_range(self.cursor, self.cursor + 1, kill=False)
            return True
        if KeyEvent["KILL_TO_END"].match(event):
            if self.has_selection():
                self._delete_selection(kill=True)
            else:
                self._delete_range(self.cursor, len(self._text), kill=True)
            return True
        if KeyEvent["KILL_TO_START"].match(event):
            if self.has_selection():
                self._delete_selection(kill=True)
            else:
                self._delete_range(0, self.cursor, kill=True)
            return True
        if KeyEvent["KILL_WORD_FORWARD"].match(event):
            if self.has_selection():
                self._delete_selection(kill=True)
            else:
                end = self._word_right(self.cursor)
                self._delete_range(self.cursor, end, kill=True)
            return True
        if KeyEvent["YANK"].match(event):
            self._insert_text(self._kill_buffer, screen_size)
            return True
        if KeyEvent["COPY"].match(event):
            try:
                set_text(self._clipboard_payload())
            except ClipboardError as exc:
                warnings.warn(
                    f"TextEntry COPY failed (clipboard set): {exc}",
                    stacklevel=2,
                )
            return True
        if KeyEvent["CUT"].match(event):
            payload = self._clipboard_payload()
            try:
                set_text(payload)
            except ClipboardError as exc:
                warnings.warn(
                    f"TextEntry CUT failed (clipboard set): {exc}",
                    stacklevel=2,
                )
                return True
            if self.has_selection():
                self._delete_selection(kill=False)
            else:
                self.clear(notify=True)
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
            clip = clip.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
            self._insert_text(clip, screen_size)
            return True
        if KeyEvent["TRANSPOSE"].match(event):
            if self.has_selection():
                self.clear_selection()
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
