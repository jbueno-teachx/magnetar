#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Compare two ui_bench JSON files; exit 1 if any key regresses beyond threshold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", type=Path)
    p.add_argument("current", type=Path)
    p.add_argument(
        "--threshold",
        type=float,
        default=0.25,
        help="Fail if current > baseline * (1 + threshold). Default 0.25 (25%%).",
    )
    args = p.parse_args()

    base = json.loads(args.baseline.read_text(encoding="utf-8"))["ms"]
    cur = json.loads(args.current.read_text(encoding="utf-8"))["ms"]

    failed = False
    print(f"{'key':32s} {'base_ms':>10s} {'cur_ms':>10s} {'delta%%':>10s} status")
    for key in sorted(set(base) | set(cur)):
        if key == "budget_60fps_ms":
            continue
        b = float(base.get(key, 0.0))
        c = float(cur.get(key, 0.0))
        if b <= 0:
            delta = 0.0 if c <= 0 else float("inf")
        else:
            delta = (c - b) / b * 100.0
        status = "ok"
        if b > 0 and c > b * (1.0 + args.threshold):
            status = "REGRESS"
            failed = True
        print(f"{key:32s} {b:10.3f} {c:10.3f} {delta:9.1f}% {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
