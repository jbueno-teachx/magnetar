# SPDX-License-Identifier: CC0-1.0
"""Optional per-frame UI / render timing hooks.

Enable with environment variable::

    MAGNETAR_PROFILE_UI=1
    MAGNETAR_PROFILE_UI=1 MAGNETAR_PROFILE_EVERY=60   # print every N frames
    MAGNETAR_PROFILE_UI=1 MAGNETAR_PROFILE_LOG=1      # append JSONL under profiling/data/

Designed to stay independent of widget internals so a future widgets spinoff
can re-home a similar API without magnetar app knowledge.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


def env_enabled(name: str = "MAGNETAR_PROFILE_UI") -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def default_data_dir() -> Path:
    """``<repo>/profiling/data`` when running from a checkout; else CWD."""
    # python/magnetar/ui_profile.py → parents[2] == repo root
    here = Path(__file__).resolve()
    repo = here.parents[2]
    candidate = repo / "profiling" / "data"
    if candidate.is_dir() or (repo / "profiling").is_dir():
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    out = Path.cwd() / "profiling" / "data"
    out.mkdir(parents=True, exist_ok=True)
    return out


@dataclass
class FrameProfiler:
    """Accumulate named timing buckets per frame and rolling window stats."""

    every: int = 60
    log_jsonl: bool = False
    data_dir: Path | None = None
    label: str = "magnetar"
    window_size: int = 300
    _frame: int = 0
    _current: dict[str, float] = field(default_factory=dict)
    _totals: dict[str, float] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)
    _window: list[dict[str, float]] = field(default_factory=list)
    _log_path: Path | None = None

    @classmethod
    def from_env(cls) -> FrameProfiler | None:
        if not env_enabled():
            return None
        return cls(
            every=_env_int("MAGNETAR_PROFILE_EVERY", 60),
            log_jsonl=env_enabled("MAGNETAR_PROFILE_LOG"),
            data_dir=default_data_dir(),
            window_size=_env_int("MAGNETAR_PROFILE_WINDOW", 300),
        )

    def __post_init__(self) -> None:
        if self.log_jsonl:
            d = self.data_dir or default_data_dir()
            d.mkdir(parents=True, exist_ok=True)
            self._log_path = d / f"ui_frames_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"

    @contextmanager
    def bucket(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self._current[name] = self._current.get(name, 0.0) + dt

    def add(self, name: str, seconds: float) -> None:
        self._current[name] = self._current.get(name, 0.0) + float(seconds)

    def end_frame(self) -> dict[str, float]:
        """Close the frame: update rolling stats, maybe print/log. Return ms map."""
        sample = dict(self._current)
        self._current.clear()
        self._frame += 1
        for k, v in sample.items():
            self._totals[k] = self._totals.get(k, 0.0) + v
            self._counts[k] = self._counts.get(k, 0) + 1
        self._window.append(sample)
        if len(self._window) > self.window_size:
            self._window.pop(0)

        ms = {k: v * 1000.0 for k, v in sample.items()}
        if self._log_path is not None:
            rec = {
                "frame": self._frame,
                "label": self.label,
                "ms": ms,
                "t": time.time(),
            }
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")

        if self.every and self._frame % self.every == 0:
            self._print_summary()
        return ms

    def rolling_means_ms(self) -> dict[str, float]:
        if not self._window:
            return {}
        keys: set[str] = set()
        for s in self._window:
            keys.update(s)
        n = len(self._window)
        out: dict[str, float] = {}
        for k in sorted(keys):
            total = sum(s.get(k, 0.0) for s in self._window)
            out[k] = (total / n) * 1000.0
        return out

    def _print_summary(self) -> None:
        means = self.rolling_means_ms()
        parts = [f"{k}={v:.3f}ms" for k, v in means.items()]
        print(
            f"[ui-profile] frame={self._frame} window={len(self._window)} " + " ".join(parts),
            flush=True,
        )


# Back-compat alias
Profiler = FrameProfiler
