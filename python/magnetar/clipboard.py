# SPDX-License-Identifier: CC0-1.0
"""System clipboard access (multi-backend).

Order of preference:

1. **Wayland** — ``wl-copy`` / ``wl-paste`` when ``WAYLAND_DISPLAY`` is set
2. **X11 tools** — ``xclip`` or ``xsel`` when available
3. **tkinter** — hidden ``Tk`` root (same-process only on many Wayland setups)

Note: ``wl-copy`` often stays alive as the clipboard *owner* and may not exit
quickly; we treat a successful subsequent ``wl-paste`` as success even if the
setter process times out.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import warnings

_root = None  # lazy tk.Tk


class ClipboardError(RuntimeError):
    """Clipboard backend unavailable or the operation failed."""


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 2.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------
# Wayland
# ---------------------------------------------------------------------------


def _wayland_active() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) and _have("wl-copy") and _have("wl-paste")


def _wl_paste_raw(timeout: float = 0.8) -> tuple[int, str, str]:
    try:
        r = _run(["wl-paste", "-n"], timeout=timeout)
        return r.returncode, r.stdout, (r.stderr or "")
    except subprocess.TimeoutExpired:
        # No owner / compositor stuck — treat as empty for readers.
        return 124, "", "timeout"


def _wayland_set(text: str) -> bool:
    if not _wayland_active():
        return False
    # Prefer argv for short payloads (avoids some stdin edge cases); fall back
    # to stdin for large / oddly encoded strings.
    try:
        if len(text) < 2000 and "\x00" not in text:
            proc = subprocess.Popen(
                ["wl-copy", "--", text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            proc = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert proc.stdin is not None
            proc.stdin.write(text)
            proc.stdin.close()
        try:
            proc.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            # Still running as clipboard provider — verify via paste.
            pass
    except OSError as exc:
        raise ClipboardError(f"wl-copy failed: {exc}") from exc

    # Confirm the compositor has our data (or at least *some* text).
    rc, out, err = _wl_paste_raw(timeout=0.8)
    if rc == 0 and out == text:
        return True
    if rc == 0 and out:
        # Something is on the clipboard but not our text — still a hard fail.
        raise ClipboardError(f"wl-copy did not stick (paste got {out[:40]!r}…, stderr={err!r})")
    # Kill a stuck failed attempt if still running.
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
    raise ClipboardError(f"wl-copy failed to publish text (paste rc={rc}, err={err!r})")


def _wayland_get() -> str | None:
    if not _wayland_active():
        return None
    rc, out, err = _wl_paste_raw(timeout=0.8)
    if rc == 124:
        return ""  # timeout → empty
    if rc != 0:
        low = err.lower()
        if "nothing" in low or "empty" in low or "no selection" in low:
            return ""
        raise ClipboardError(f"wl-paste failed: {err.strip() or rc}")
    return out


# ---------------------------------------------------------------------------
# X11 CLI
# ---------------------------------------------------------------------------


def _x11_set(text: str) -> bool:
    if _have("xclip"):
        try:
            r = _run(["xclip", "-selection", "clipboard"], input_text=text)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClipboardError(f"xclip set failed: {exc}") from exc
        if r.returncode != 0:
            raise ClipboardError(f"xclip set failed: {r.stderr.strip() or r.returncode}")
        return True
    if _have("xsel"):
        try:
            r = _run(["xsel", "--clipboard", "--input"], input_text=text)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClipboardError(f"xsel set failed: {exc}") from exc
        if r.returncode != 0:
            raise ClipboardError(f"xsel set failed: {r.stderr.strip() or r.returncode}")
        return True
    return False


def _x11_get() -> str | None:
    if _have("xclip"):
        try:
            r = _run(["xclip", "-selection", "clipboard", "-o"], timeout=1.0)
        except subprocess.TimeoutExpired:
            return ""
        except OSError as exc:
            raise ClipboardError(f"xclip get failed: {exc}") from exc
        return r.stdout if r.returncode == 0 else ""
    if _have("xsel"):
        try:
            r = _run(["xsel", "--clipboard", "--output"], timeout=1.0)
        except subprocess.TimeoutExpired:
            return ""
        except OSError as exc:
            raise ClipboardError(f"xsel get failed: {exc}") from exc
        return r.stdout if r.returncode == 0 else ""
    return None


# ---------------------------------------------------------------------------
# tkinter fallback
# ---------------------------------------------------------------------------


def _ensure_root():
    global _root
    import tkinter as tk

    if _root is not None:
        try:
            _root.winfo_exists()
            return _root
        except tk.TclError:
            _root = None
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise ClipboardError(f"tkinter display unavailable: {exc}") from exc
    root.withdraw()
    try:
        root.overrideredirect(True)
    except tk.TclError:
        pass
    _root = root
    return root


def reset() -> None:
    """Destroy the hidden Tk root (for tests)."""
    global _root
    if _root is not None:
        try:
            _root.destroy()
        except Exception:
            pass
        _root = None


def _tk_set(text: str) -> None:
    import tkinter as tk

    root = _ensure_root()
    try:
        root.clipboard_clear()
        root.clipboard_append(str(text))
        root.update_idletasks()
        root.update()
    except tk.TclError as exc:
        raise ClipboardError(f"tkinter clipboard set failed: {exc}") from exc


def _tk_get() -> str:
    import tkinter as tk
    from tkinter import TclError

    root = _ensure_root()
    try:
        root.update_idletasks()
        root.update()
        return str(root.clipboard_get())
    except TclError:
        return ""
    except tk.TclError as exc:
        raise ClipboardError(f"tkinter clipboard get failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backend_name() -> str:
    """Name of the preferred backend for this environment."""
    if _wayland_active():
        return "wayland-wl-clipboard"
    if _have("xclip") or _have("xsel"):
        return "x11-cli"
    return "tkinter"


def set_text(text: str) -> None:
    """Copy ``text`` to the system clipboard."""
    text = str(text)
    errors: list[str] = []

    for name, fn in (
        ("wayland", _wayland_set),
        ("x11", _x11_set),
    ):
        try:
            if fn(text):
                return
        except ClipboardError as exc:
            errors.append(f"{name}: {exc}")

    try:
        _tk_set(text)
    except ClipboardError as exc:
        errors.append(f"tkinter: {exc}")
        raise ClipboardError(
            "all clipboard backends failed for set_text: " + "; ".join(errors)
        ) from exc

    if _wayland_active() or errors:
        warnings.warn(
            "clipboard set fell back to tkinter; other apps (esp. on Wayland) "
            f"may not see it. prior errors: {errors or 'n/a'}",
            stacklevel=2,
        )


def get_text() -> str:
    """Return clipboard text, or ``\"\"`` if empty / non-text."""
    errors: list[str] = []

    for name, fn in (
        ("wayland", _wayland_get),
        ("x11", _x11_get),
    ):
        try:
            val = fn()
            if val is not None:
                return val
        except ClipboardError as exc:
            errors.append(f"{name}: {exc}")

    try:
        return _tk_get()
    except ClipboardError as exc:
        errors.append(f"tkinter: {exc}")
        raise ClipboardError(
            "all clipboard backends failed for get_text: " + "; ".join(errors)
        ) from exc


def available() -> bool:
    """True if any clipboard backend looks usable."""
    if _wayland_active():
        return True
    if _have("xclip") or _have("xsel"):
        return True
    try:
        _ensure_root()
        return True
    except ClipboardError:
        return False
