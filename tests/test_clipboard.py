# SPDX-License-Identifier: CC0-1.0
"""Clipboard backend and TextEntry copy/paste bindings."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from unittest.mock import patch

import pygame
import pytest

from magnetar import clipboard
from magnetar.widgets import KeyEvent, TextEntry


def _keydown(key: int, uni: str = "", *, mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=mod)


def test_key_event_copy_paste_combos() -> None:
    assert KeyEvent["COPY"].match(_keydown(pygame.K_c, mod=pygame.KMOD_CTRL))
    assert KeyEvent["COPY"].match(_keydown(pygame.K_c, mod=pygame.KMOD_CTRL | pygame.KMOD_SHIFT))
    assert KeyEvent["COPY"].match(_keydown(pygame.K_c, mod=pygame.KMOD_META))
    assert KeyEvent["COPY"].match(_keydown(pygame.K_c, mod=pygame.KMOD_GUI))
    assert not KeyEvent["COPY"].match(_keydown(pygame.K_c, "c"))
    assert KeyEvent["PASTE"].match(_keydown(pygame.K_v, mod=pygame.KMOD_CTRL))
    assert KeyEvent["PASTE"].match(_keydown(pygame.K_v, mod=pygame.KMOD_META))
    assert KeyEvent["PASTE"].match(_keydown(pygame.K_INSERT, mod=pygame.KMOD_SHIFT))


def test_text_entry_copy_paste_via_mock_clipboard() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="hello")
        entry.focus()
        entry.cursor = 5
        size = (800, 60)
        store: dict[str, str] = {}

        def fake_set(s: str) -> None:
            store["t"] = s

        def fake_get() -> str:
            return store.get("t", "")

        with (
            patch("magnetar.widgets.set_text", side_effect=fake_set),
            patch("magnetar.widgets.get_text", side_effect=fake_get),
        ):
            assert entry.handle_key(_keydown(pygame.K_c, mod=pygame.KMOD_CTRL), size)
            assert store["t"] == "hello"
            # Ctrl+Shift+C also copies
            store.clear()
            assert entry.handle_key(
                _keydown(pygame.K_c, mod=pygame.KMOD_CTRL | pygame.KMOD_SHIFT), size
            )
            assert store["t"] == "hello"
            # Cmd+C
            store.clear()
            assert entry.handle_key(_keydown(pygame.K_c, mod=pygame.KMOD_GUI), size)
            assert store["t"] == "hello"

            store["t"] = "XY"
            entry.cursor = 2  # he|llo
            assert entry.handle_key(_keydown(pygame.K_v, mod=pygame.KMOD_CTRL), size)
            assert entry.text == "heXYllo"
            assert entry.cursor == 4
    finally:
        pygame.display.quit()


def test_text_entry_paste_flattens_newlines() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="")
        entry.focus()
        size = (800, 60)
        with patch("magnetar.widgets.get_text", return_value="a\nb\r\nc"):
            entry.handle_key(_keydown(pygame.K_v, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "a b c"
    finally:
        pygame.display.quit()


@pytest.mark.clipboard
def test_tkinter_clipboard_roundtrip() -> None:
    """Real OS clipboard via tkinter — skip when no display / Tk."""
    clipboard.reset()
    if not clipboard.available():
        pytest.skip("tkinter clipboard unavailable (no display / Tk)")
    try:
        clipboard.set_text("magnetar-clip-test")
        assert clipboard.get_text() == "magnetar-clip-test"
    finally:
        clipboard.reset()
