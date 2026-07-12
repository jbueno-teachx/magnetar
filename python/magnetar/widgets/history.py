# SPDX-License-Identifier: CC0-1.0
"""Disk-backed command history for :class:`HistoryTextEntry`.

Files live under ``~/.config/magnetar/history/<name>.json`` (override with
env ``MAGNETAR_HISTORY_DIR``). Loaded on first use; saved only via
:func:`save_all_histories` (called from :func:`magnetar.widgets.quit`).
"""

from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path

DEFAULT_MAX_ENTRIES = 200

# name -> store (process-wide; flushed at widgets.quit)
_REGISTRY: dict[str, "HistoryStore"] = {}


def history_dir() -> Path:
    override = os.environ.get("MAGNETAR_HISTORY_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "magnetar" / "history"


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", str(name).strip()) or "default"
    return cleaned[:120]


class HistoryStore:
    """Ordered list of history lines (oldest → newest), max length capped."""

    def __init__(self, name: str, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self.name = str(name)
        self.max_entries = max(1, int(max_entries))
        self.entries: list[str] = []
        self._load()

    @property
    def path(self) -> Path:
        return history_dir() / f"{_safe_filename(self.name)}.json"

    def _load(self) -> None:
        path = self.path
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                raw = data["entries"]
            elif isinstance(data, list):
                raw = data
            else:
                return
            lines = [str(x) for x in raw if str(x)]
            self.entries = lines[-self.max_entries :]
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"history load failed for {self.name!r} ({path}): {exc}",
                stacklevel=2,
            )

    def save(self) -> None:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"name": self.name, "entries": self.entries[-self.max_entries :]}
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"history save failed for {self.name!r} ({path}): {exc}",
                stacklevel=2,
            )

    def add(self, line: str) -> None:
        """Append a submitted line (skip empty / consecutive duplicates)."""
        text = str(line)
        if not text.strip():
            return
        if self.entries and self.entries[-1] == text:
            return
        self.entries.append(text)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, index: int) -> str:
        return self.entries[index]


def get_store(name: str, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> HistoryStore:
    """Return the process-wide store for ``name`` (load once)."""
    key = str(name)
    store = _REGISTRY.get(key)
    if store is None:
        store = HistoryStore(key, max_entries=max_entries)
        _REGISTRY[key] = store
    return store


def save_all_histories() -> None:
    """Persist every registered store (called at widgets.quit)."""
    for store in list(_REGISTRY.values()):
        store.save()


def reset_registry_for_tests() -> None:
    """Drop in-memory stores (tests only). Does not delete files."""
    _REGISTRY.clear()
