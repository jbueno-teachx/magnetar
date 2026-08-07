---
name: magnetar-dev
description: >
  Run magnetar the standard way: env314 venv, pytest, ruff, app launch, UI
  bench. Use when adding features, running tests, linting, profiling, or the
  user runs /magnetar-dev. Not for theme-key wiring (use /widget-theme).
metadata:
  short-description: "Magnetar test / lint / run loop"
---

# magnetar-dev — local build-test loop

## Environment

Always:

```bash
source env314/bin/activate
```

- Python **3.14** from `env314/`. Do not create `.venv` or `venv/`.
- Install/edit: `pip install -e ".[dev]"` (adds pytest + ruff). Optional OpenGL: `".[opengl]"`.
- `SDL_AUDIODRIVER=dummy` is set in app/world on purpose.

## Verify after code changes

Default gate (from repo root):

```bash
source env314/bin/activate
ruff check python tests
pytest -q
```

Narrow when the change is local:

| Area | Extra tests |
|------|-------------|
| Theme / chrome | `pytest tests/test_theme.py tests/test_widgets.py tests/test_textpanel.py -q` and follow `/widget-theme` |
| Prompt / DSL | `tests/test_prompt.py` |
| World / particles | `tests/test_world.py` `tests/test_particle_sprites.py` `tests/test_screen_sprite.py` |
| Clipboard | `tests/test_clipboard.py` (may skip without display/tk) |
| View | `tests/test_view3d.py` |

Do not claim done if ruff or the relevant pytest file fails.

## Run the app

```bash
source env314/bin/activate
python -m magnetar
# or: magnetar
```

Needs a display. Prompt is **in-window** (`HistoryTextEntry`), not a separate stdin TTY.

## Profiling

Only when draw/event cost might change:

```bash
python profiling/scripts/run_ui_bench.py
# live:
MAGNETAR_PROFILE_UI=1 magnetar
```

Do not refresh `profiling/data/baselines/` unless the user asks.

## Rust

`Cargo.toml` / `src/` are a **future** port. Do not add a cargo CI gate or rewrite Python into Rust unless the task is explicitly that port.

## Theme / widgets

New theme attributes or styled widgets → stop and follow **`/widget-theme`**. This skill does not replace it.

## Style

- Line length 100, `target-version = "py314"`
- New `.py` files: `# SPDX-License-Identifier: CC0-1.0`
- Keep `default_theme.py` copyable (no magnetar imports)
