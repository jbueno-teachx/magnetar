# SPDX-License-Identifier: CC0-1.0
"""FrameProfiler hooks."""

import json
from pathlib import Path

from magnetar.ui_profile import FrameProfiler, env_enabled


def test_env_enabled(monkeypatch) -> None:
    monkeypatch.delenv("MAGNETAR_PROFILE_UI", raising=False)
    assert env_enabled() is False
    monkeypatch.setenv("MAGNETAR_PROFILE_UI", "1")
    assert env_enabled() is True


def test_buckets_and_rolling(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MAGNETAR_PROFILE_UI", "1")
    monkeypatch.setenv("MAGNETAR_PROFILE_EVERY", "1000")
    p = FrameProfiler(every=1000, log_jsonl=True, data_dir=tmp_path, window_size=10)
    with p.bucket("a"):
        pass
    with p.bucket("b"):
        pass
    ms = p.end_frame()
    assert "a" in ms and "b" in ms
    means = p.rolling_means_ms()
    assert "a" in means
    logs = list(tmp_path.glob("ui_frames_*.jsonl"))
    assert logs
    line = logs[0].read_text(encoding="utf-8").strip().splitlines()[0]
    rec = json.loads(line)
    assert rec["frame"] == 1
    assert "ms" in rec


def test_from_env_off(monkeypatch) -> None:
    monkeypatch.delenv("MAGNETAR_PROFILE_UI", raising=False)
    assert FrameProfiler.from_env() is None
