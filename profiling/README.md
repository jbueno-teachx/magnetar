# Profiling (magnetar)

Helpers and durable data for UI / frame timing. Used to catch regressions
before and after widget caching work.

## Runtime hooks

In the package: `magnetar.ui_profile.FrameProfiler`.

Enable while running the app:

```bash
source env314/bin/activate
MAGNETAR_PROFILE_UI=1 magnetar
# print rolling means every 60 frames (default)
MAGNETAR_PROFILE_UI=1 MAGNETAR_PROFILE_EVERY=30 magnetar
# also append JSONL samples under profiling/data/
MAGNETAR_PROFILE_UI=1 MAGNETAR_PROFILE_LOG=1 magnetar
```

Buckets recorded each frame (when enabled):

| Bucket | Meaning |
|--------|---------|
| `events` | pygame / widget event dispatch |
| `world_step` | simulation step |
| `world_draw` | clear + axes + particles |
| `hud_update` | status `TextPanel.set_lines` only |
| `widgets_draw` | full widget registry paint |
| `widget.<name>` | per-widget `draw` (when registry profiling on) |
| `flip` | `pygame.display.flip` |
| `frame` | whole loop body after clock.tick |

## Offline micro-bench

```bash
python profiling/scripts/run_ui_bench.py
python profiling/scripts/run_ui_bench.py --out profiling/data/ui_bench_latest.json
```

## Data layout

```text
profiling/data/
  ui_bench_*.json     # offline bench snapshots
  ui_frames_*.jsonl   # optional per-frame logs from a live session
  baselines/          # checked-in reference numbers (optional)
```

Large raw dumps may be gitignored; keep small baselines under `baselines/`.

## Regression check

```bash
python profiling/scripts/compare_bench.py \
  profiling/data/baselines/ui_bench_baseline.json \
  profiling/data/ui_bench_latest.json
```
