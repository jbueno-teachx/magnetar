# SPDX-License-Identifier: CC0-1.0
"""Text entry with navigable, disk-backed history."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.widgets.base import AnchorLike, Command, ScreenSize
from magnetar.widgets.history import DEFAULT_MAX_ENTRIES, HistoryStore, get_store
from magnetar.widgets.keyevent import KeyEvent
from magnetar.widgets.textentry import TextEntry


class HistoryTextEntry(TextEntry):
    """:class:`TextEntry` plus up/down history and Ctrl+R reverse search.

    Parameters
    ----------
    name:
        Stable id for disk persistence (``~/.config/magnetar/history/<name>.json``).
    max_entries:
        Cap on retained lines (default 200). Not a ring: navigation stops at the
        oldest / newest entry.
    """

    def __init__(
        self,
        x_pct: float,
        y_pct: float,
        w_pct: float,
        h_pct: float,
        *,
        name: str,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        anchor: AnchorLike = None,
        font: pygame.font.Font | None = None,
        text: str = "",
        placeholder: str = "",
        command: Command = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            x_pct,
            y_pct,
            w_pct,
            h_pct,
            anchor=anchor,
            font=font,
            text=text,
            placeholder=placeholder,
            name=name,
            command=command,
            **kwargs,  # type: ignore[arg-type]
        )
        self.history_name = str(name)
        self._store: HistoryStore = get_store(self.history_name, max_entries=max_entries)
        # None = editing the live draft; int = index into history (0 = oldest).
        self._hist_idx: int | None = None
        self._draft: str = ""
        # Reverse-i-search state
        self._search_mode = False
        self._search_query = ""
        self._search_pos: int | None = None  # index of current match (or None)

    # -- history navigation ---------------------------------------------------

    def _load_history_line(self, index: int) -> None:
        self._hist_idx = index
        line = self._store.entries[index]
        self.text = line
        self.cursor = len(line)
        self.clear_selection()
        self._nudge_caret()

    def _history_up(self) -> None:
        if self._search_mode:
            return
        n = len(self._store)
        if n == 0:
            return
        if self._hist_idx is None:
            self._draft = self.text
            self._load_history_line(n - 1)
            return
        if self._hist_idx > 0:
            self._load_history_line(self._hist_idx - 1)
        # else already at oldest — do not wrap

    def _history_down(self) -> None:
        if self._search_mode:
            return
        n = len(self._store)
        if self._hist_idx is None or n == 0:
            return
        if self._hist_idx < n - 1:
            self._load_history_line(self._hist_idx + 1)
            return
        # Past newest → restore live draft
        self._hist_idx = None
        self.text = self._draft
        self.cursor = len(self._text)
        self.clear_selection()
        self._nudge_caret()

    def _commit_to_history(self) -> None:
        self._store.add(self.text)
        self._hist_idx = None
        self._draft = ""
        self._exit_search(restore_draft=False)

    # -- Ctrl+R reverse search ------------------------------------------------

    def _enter_search(self) -> None:
        if not self._search_mode:
            self._draft = self.text if self._hist_idx is None else self._draft
            self._search_mode = True
            self._search_query = ""
            self._search_pos = None
        self._search_backward(from_start=self._search_pos is None)

    def _exit_search(self, *, restore_draft: bool) -> None:
        was = self._search_mode
        self._search_mode = False
        self._search_query = ""
        self._search_pos = None
        if was and restore_draft:
            self._hist_idx = None
            self.text = self._draft
            self.cursor = len(self._text)
            self.clear_selection()
            self._nudge_caret()

    def _search_backward(self, *, from_start: bool) -> None:
        entries = self._store.entries
        if not entries:
            return
        q = self._search_query
        # Start just before current match (or at end for first search).
        if from_start or self._search_pos is None:
            start = len(entries) - 1
        else:
            start = self._search_pos - 1
        for i in range(start, -1, -1):
            if q == "" or q in entries[i]:
                self._search_pos = i
                self._load_history_line(i)
                return
        # No older match: keep current field

    def _handle_search_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        if KeyEvent["HISTORY_SEARCH"].match(event):
            self._search_backward(from_start=False)
            return True
        if KeyEvent["BLUR"].match(event) or event.key == pygame.K_ESCAPE:
            self._exit_search(restore_draft=True)
            return True
        if KeyEvent["SUBMIT"].match(event):
            # Accept match into the field, leave search, then submit.
            self._exit_search(restore_draft=False)
            self._commit_to_history()
            return super().handle_key(event, screen_size)
        if KeyEvent["BACKSPACE"].match(event):
            if self._search_query:
                self._search_query = self._search_query[:-1]
                self._search_pos = None
                self._search_backward(from_start=True)
            return True
        # Printable refines the query
        ch = getattr(event, "unicode", "") or ""
        mods = int(getattr(event, "mod", 0) or 0)
        if (mods & KeyEvent._CHORD_MODS) == 0 and ch and ch.isprintable() and ch not in "\r\n\t":
            self._search_query += ch
            self._search_pos = None
            self._search_backward(from_start=True)
            return True
        # Swallow other keys in search mode
        return True

    # -- keyboard -------------------------------------------------------------

    def handle_key(self, event: pygame.event.Event, screen_size: ScreenSize) -> bool:
        if not self.focused or not self.enabled or not self.visible:
            return False
        if event.type != pygame.KEYDOWN:
            return False

        if self._search_mode:
            return self._handle_search_key(event, screen_size)

        if KeyEvent["HISTORY_UP"].match(event):
            self._history_up()
            return True
        if KeyEvent["HISTORY_DOWN"].match(event):
            self._history_down()
            return True
        if KeyEvent["HISTORY_SEARCH"].match(event):
            self._enter_search()
            return True

        if KeyEvent["SUBMIT"].match(event):
            self._commit_to_history()
            return super().handle_key(event, screen_size)

        # Editing while browsing history stays on that line (does not mutate store).
        return super().handle_key(event, screen_size)
