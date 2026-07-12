# SPDX-License-Identifier: CC0-1.0
"""Single-line text entry widget."""

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
    Widget,
    WidgetPointerEvent,
)
from magnetar.widgets.clipboard import ClipboardError, get_text, set_text
from magnetar.widgets.keyevent import KeyEvent


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
