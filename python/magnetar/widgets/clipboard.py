# SPDX-License-Identifier: CC0-1.0
"""System clipboard via a dedicated tkinter mainloop thread.

All Tk calls run on one background thread. Callers use :func:`set_text` /
:func:`get_text`, which enqueue work and wait for a reply. A 10 ms ``after``
tick drains the queue. :func:`shutdown` enqueues a poison pill and joins the
thread (call from app teardown next to ``pygame.quit()``).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import TclError
from typing import Any, Literal

# Poll period for the Tk-side queue pump (ms).
_POLL_MS = 30
# How long callers wait for a set/get to finish.
_CALL_TIMEOUT_S = 5.0
# How long we wait for the worker to come up / die.
_START_TIMEOUT_S = 5.0
_JOIN_TIMEOUT_S = 2.0

_Op = Literal["set", "get"]


class ClipboardError(RuntimeError):
    """Clipboard backend unavailable or the operation failed."""


@dataclass
class _Job:
    op: _Op
    text: str = ""
    reply: queue.Queue[tuple[bool, Any]] = field(default_factory=queue.Queue)


class _Poison:
    """Sentinel: stop the Tk mainloop (same queue as work items)."""

    def __repr__(self) -> str:
        return "<clipboard.POISON>"


_POISON = _Poison()

_QueueItem = _Job | _Poison


class _ClipboardWorker:
    """Owns the Tk root, queue, and mainloop thread."""

    def __init__(self) -> None:
        self._jobs: queue.Queue[_QueueItem] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root: tk.Tk | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._lock = threading.Lock()
        self._alive = False

    # -- lifecycle ------------------------------------------------------------

    def ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._alive:
                return
            # Fresh start after shutdown / failed boot.
            self._ready.clear()
            self._start_error = None
            self._alive = False
            self._jobs = queue.Queue()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="magnetar-widgets-clipboard-tk",
                daemon=True,
            )
            self._thread.start()

        if not self._ready.wait(timeout=_START_TIMEOUT_S):
            raise ClipboardError("clipboard Tk thread failed to start (timeout)")
        if self._start_error is not None:
            raise ClipboardError(
                f"clipboard Tk thread failed to start: {self._start_error}"
            ) from self._start_error
        if not self._alive:
            raise ClipboardError("clipboard Tk thread started but is not alive")

    def shutdown(self) -> None:
        """Poison the queue, quit mainloop, join the thread."""
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._thread = None
                self._root = None
                self._alive = False
                return
            self._jobs.put(_POISON)
        thread.join(timeout=_JOIN_TIMEOUT_S)
        with self._lock:
            if thread.is_alive():
                # Last resort: try to quit from outside (best-effort).
                root = self._root
                if root is not None:
                    try:
                        root.after(0, root.quit)
                    except Exception:
                        pass
                thread.join(timeout=0.5)
            self._thread = None
            self._root = None
            self._alive = False

    # -- Tk thread ------------------------------------------------------------

    def _thread_main(self) -> None:
        try:
            root = tk.Tk()
            root.withdraw()
            try:
                root.overrideredirect(True)
            except tk.TclError:
                pass
            self._root = root
            self._alive = True
            self._ready.set()
            root.after(_POLL_MS, self._pump)
            root.mainloop()
        except BaseException as exc:
            self._start_error = exc
            self._alive = False
            self._ready.set()
        finally:
            self._alive = False
            root = self._root
            self._root = None
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def _pump(self) -> None:
        """Drain the request queue; reschedule every ``_POLL_MS`` unless poisoned."""
        root = self._root
        if root is None:
            return
        stop = False
        try:
            while True:
                try:
                    item = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, _Poison):
                    stop = True
                    break
                self._run_job(item)
        except Exception:
            # Keep the loop alive on unexpected pump errors.
            pass

        if stop:
            try:
                root.quit()
            except Exception:
                pass
            return

        try:
            root.after(_POLL_MS, self._pump)
        except tk.TclError:
            pass

    def _run_job(self, job: _Job) -> None:
        root = self._root
        assert root is not None
        try:
            if job.op == "set":
                root.clipboard_clear()
                root.clipboard_append(str(job.text))
                # mainloop is running; idle tasks still help some platforms.
                root.update_idletasks()
                job.reply.put((True, None))
            elif job.op == "get":
                try:
                    text = str(root.clipboard_get())
                except TclError:
                    text = ""
                job.reply.put((True, text))
            else:
                job.reply.put((False, ClipboardError(f"unknown op {job.op!r}")))
        except Exception as exc:
            try:
                job.reply.put((False, exc))
            except Exception:
                pass

    # -- caller API (any thread) ----------------------------------------------

    def set_text(self, text: str) -> None:
        self.ensure_started()
        job = _Job(op="set", text=str(text))
        self._jobs.put(job)
        self._wait(job, "set")

    def get_text(self) -> str:
        self.ensure_started()
        job = _Job(op="get")
        self._jobs.put(job)
        result = self._wait(job, "get")
        return "" if result is None else str(result)

    def _wait(self, job: _Job, label: str) -> Any:
        try:
            ok, payload = job.reply.get(timeout=_CALL_TIMEOUT_S)
        except queue.Empty as exc:
            raise ClipboardError(
                f"clipboard {label} timed out after {_CALL_TIMEOUT_S}s (Tk thread not processing?)"
            ) from exc
        if not ok:
            if isinstance(payload, BaseException):
                raise ClipboardError(f"clipboard {label} failed: {payload}") from payload
            raise ClipboardError(f"clipboard {label} failed: {payload}")
        return payload


_worker = _ClipboardWorker()


def set_text(text: str) -> None:
    """Copy ``text`` to the system clipboard (via the Tk worker thread)."""
    _worker.set_text(text)


def get_text() -> str:
    """Return clipboard text, or ``\"\"`` if empty / non-text."""
    return _worker.get_text()


def available() -> bool:
    """True if the Tk clipboard worker can start."""
    try:
        _worker.ensure_started()
        return True
    except ClipboardError:
        return False


def backend_name() -> str:
    return "tkinter-mainloop-thread"


def shutdown() -> None:
    """Stop the Tk mainloop thread (poison pill + join)."""
    _worker.shutdown()


def reset() -> None:
    """Alias for :func:`shutdown` (tests / re-init)."""
    shutdown()
