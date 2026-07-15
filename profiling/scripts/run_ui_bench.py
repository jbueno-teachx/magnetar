#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Offline UI micro-bench → JSON under profiling/data/."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=200)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "profiling" / "data" / "ui_bench_latest.json",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Also write profiling/data/baselines/ui_bench_baseline.json",
    )
    args = parser.parse_args()

    import pygame

    from magnetar.app import MagnetarApp
    from magnetar.assets import DEFAULT_HUD_FONT_SIZE, hud_font_path

    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.display.set_mode((1024, 768))
        app = MagnetarApp()
        with hud_font_path() as font_file:
            app.font = pygame.font.Font(str(font_file), DEFAULT_HUD_FONT_SIZE)
        from magnetar.widgets import get_theme

        get_theme().font = app.font
        app.screen = screen
        app._build_ui()
        assert app._hud_panel is not None and app._prompt_out is not None

        def timed(fn, n: int) -> float:
            for _ in range(5):
                fn()
            t0 = time.perf_counter()
            for _ in range(n):
                fn()
            return (time.perf_counter() - t0) / n * 1000.0

        n = args.frames
        results: dict[str, float] = {}

        results["draw_hud_ms"] = timed(app.draw_hud, n)
        results["hud_panel_draw_ms"] = timed(lambda: app._hud_panel.draw(screen), n)
        results["widgets_draw_hidden_out_ms"] = timed(lambda: app.widgets.draw(screen), n)

        app._append_prompt_output("bench\n" + "\n".join(f"line {i}" for i in range(20)))
        results["widgets_draw_open_out_ms"] = timed(lambda: app.widgets.draw(screen), n)
        results["prompt_out_draw_ms"] = timed(lambda: app._prompt_out.draw(screen), n)
        results["render_frame_ms"] = timed(app.render_frame, n)

        def full_flip():
            app.render_frame()
            pygame.display.flip()

        results["render_frame_flip_ms"] = timed(full_flip, n)
        results["budget_60fps_ms"] = 1000.0 / 60.0

        payload = {
            "meta": {
                "frames": n,
                "resolution": [1024, 768],
                "pygame": pygame.version.ver,
                "python": sys.version.split()[0],
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            "ms": results,
        }

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        print(f"wrote {args.out}", file=sys.stderr)

        if args.baseline:
            base = ROOT / "profiling" / "data" / "baselines" / "ui_bench_baseline.json"
            base.parent.mkdir(parents=True, exist_ok=True)
            base.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {base}", file=sys.stderr)
        return 0
    finally:
        pygame.font.quit()
        pygame.display.quit()


if __name__ == "__main__":
    raise SystemExit(main())
