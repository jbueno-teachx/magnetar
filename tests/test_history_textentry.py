# SPDX-License-Identifier: CC0-1.0
"""HistoryTextEntry navigation, search, and disk persistence."""

from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from magnetar.widgets.history import get_store, reset_registry_for_tests, save_all_histories
from magnetar.widgets.history_textentry import HistoryTextEntry
from magnetar.widgets.keyevent import KeyEvent


def _keydown(key: int, uni: str = "", *, mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=mod)


@pytest.fixture()
def hist_dir(tmp_path, monkeypatch):
    d = tmp_path / "history"
    monkeypatch.setenv("MAGNETAR_HISTORY_DIR", str(d))
    reset_registry_for_tests()
    yield d
    reset_registry_for_tests()


def test_history_up_down_no_wrap(hist_dir) -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        e = HistoryTextEntry(0, 0, 100, 20, name="t1", font=pygame.font.Font(None, 20))
        e.focus()
        size = (800, 40)
        for line in ("one", "two", "three"):
            e.text = line
            e.handle_key(_keydown(pygame.K_RETURN), size)
            e.clear(notify=False)
        assert list(e._store.entries) == ["one", "two", "three"]

        e.text = "draft"
        e.handle_key(_keydown(pygame.K_UP), size)
        assert e.text == "three"
        e.handle_key(_keydown(pygame.K_UP), size)
        assert e.text == "two"
        e.handle_key(_keydown(pygame.K_UP), size)
        assert e.text == "one"
        e.handle_key(_keydown(pygame.K_UP), size)
        assert e.text == "one"  # no wrap

        e.handle_key(_keydown(pygame.K_DOWN), size)
        assert e.text == "two"
        e.handle_key(_keydown(pygame.K_DOWN), size)
        assert e.text == "three"
        e.handle_key(_keydown(pygame.K_DOWN), size)
        assert e.text == "draft"  # live draft
        e.handle_key(_keydown(pygame.K_DOWN), size)
        assert e.text == "draft"  # no wrap past draft
    finally:
        pygame.display.quit()


def test_history_max_200(hist_dir) -> None:
    store = get_store("cap", max_entries=200)
    for i in range(250):
        store.add(f"line-{i}")
    assert len(store) == 200
    assert store.entries[0] == "line-50"
    assert store.entries[-1] == "line-249"


def test_history_persist_on_save_all(hist_dir) -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        e = HistoryTextEntry(0, 0, 100, 20, name="persist", font=pygame.font.Font(None, 20))
        e.focus()
        size = (400, 40)
        e.text = "saved-line"
        e.handle_key(_keydown(pygame.K_RETURN), size)
        save_all_histories()
        path = hist_dir / "persist.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "saved-line" in data["entries"]

        reset_registry_for_tests()
        e2 = HistoryTextEntry(0, 0, 100, 20, name="persist", font=pygame.font.Font(None, 20))
        assert e2._store.entries[-1] == "saved-line"
    finally:
        pygame.display.quit()


def test_history_ctrl_r_search(hist_dir) -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        e = HistoryTextEntry(0, 0, 100, 20, name="search", font=pygame.font.Font(None, 20))
        e.focus()
        size = (800, 40)
        for line in ("apple pie", "banana", "pineapple", "grape"):
            e.text = line
            e.handle_key(_keydown(pygame.K_RETURN), size)
            e.clear(notify=False)

        # Ctrl+R then type "app" → pineapple (newest match), Ctrl+R again → apple pie
        assert e.handle_key(_keydown(pygame.K_r, mod=pygame.KMOD_CTRL), size)
        assert e._search_mode
        e.handle_key(_keydown(pygame.K_a, "a"), size)
        e.handle_key(_keydown(pygame.K_p, "p"), size)
        e.handle_key(_keydown(pygame.K_p, "p"), size)
        assert "app" in e.text
        assert e.text == "pineapple"
        e.handle_key(_keydown(pygame.K_r, mod=pygame.KMOD_CTRL), size)
        assert e.text == "apple pie"
    finally:
        pygame.display.quit()


def test_history_search_keyevent() -> None:
    assert KeyEvent["HISTORY_UP"].match(_keydown(pygame.K_UP))
    assert KeyEvent["HISTORY_DOWN"].match(_keydown(pygame.K_DOWN))
    assert KeyEvent["HISTORY_SEARCH"].match(_keydown(pygame.K_r, mod=pygame.KMOD_CTRL))
