# SPDX-License-Identifier: CC0-1.0
"""System clipboard access via a hidden tkinter root (no mainloop).

Uses ``Tk().withdraw()`` and ``update()`` only — multi-platform when Tk can
open a display. Desktop Linux needs Tk (e.g. ``python3-tk``); headless CI
without a display may fail (callers should handle :class:`ClipboardError`).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import TclError

_root: tk.Tk | None = None


class ClipboardError(RuntimeError):
    """Clipboard backend unavailable or the operation failed."""


def _ensure_root() -> tk.Tk:
    """Return a process-wide withdrawn ``Tk`` instance."""
    global _root
    if _root is not None:
        try:
            # Detect destroyed roots.
            _root.winfo_exists()
            return _root
        except tk.TclError:
            _root = None
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise ClipboardError(f"tkinter display unavailable: {exc}") from exc
    root.withdraw()
    # Avoid the window showing up in some WMs if withdraw is delayed.
    try:
        root.overrideredirect(True)
    except tk.TclError:
        pass
    _root = root
    return root


def reset() -> None:
    """Destroy the hidden root (for tests)."""
    global _root
    if _root is not None:
        try:
            _root.destroy()
        except tk.TclError:
            pass
        _root = None


def set_text(text: str) -> None:
    """Copy ``text`` to the system clipboard."""
    root = _ensure_root()
    try:
        root.clipboard_clear()
        root.clipboard_append(str(text))
        # Push to the OS clipboard; required on many platforms.
        root.update()
    except tk.TclError as exc:
        raise ClipboardError(f"clipboard set failed: {exc}") from exc


def get_text() -> str:
    """Return clipboard text, or ``\"\"`` if empty / non-text."""
    root = _ensure_root()
    try:
        root.update()
        return str(root.clipboard_get())
    except TclError:
        # Empty clipboard or non-string type.
        return ""
    except tk.TclError as exc:
        raise ClipboardError(f"clipboard get failed: {exc}") from exc


def available() -> bool:
    """True if a hidden Tk root can be created (clipboard backend usable)."""
    try:
        _ensure_root()
        return True
    except ClipboardError:
        return False
