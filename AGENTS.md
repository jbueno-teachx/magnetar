# Agent notes — magnetar

## Identity

- Project: **magnetar** — 3D electric / magnetic particle simulator
- License: **CC0-1.0** (put `# SPDX-License-Identifier: CC0-1.0` on new Python files)
- Git remote: `git@github.com:jbueno-teachx/magnetar.git`
- GitHub: https://github.com/jbueno-teachx/magnetar
- Runtime: **Python 3.14+** and **pygame-ce**. Rust (`Cargo.toml`, `src/`) is reserved for a later port — not the active path.

## Layout

| Path | Role |
|------|------|
| `python/magnetar/` | Installable package |
| `python/magnetar/app.py` | pygame main loop + view constants |
| `python/magnetar/world.py` | 3D particle space |
| `python/magnetar/particles.py` | Physics types + sprite display types |
| `python/magnetar/prompt.py` | In-window command dispatcher (not a stdin TTY) |
| `python/magnetar/widgets/` | UI widgets + theme |
| `python/magnetar/assets/` | Fonts + particle sprites |
| `tests/` | pytest (`pythonpath = ["python"]`) |
| `profiling/` | UI / frame benches |
| `image_scripts/` | POV-Ray helpers for particle sprites |
| `.grok/skills/` | Project Grok skills |
| `.grok/config.toml` | Project MCP servers |

## Commands

Use the existing venv. Do not create another `.venv`.

```bash
source env314/bin/activate
pip install -e ".[dev]"
python -m magnetar          # or: magnetar
pytest -q
ruff check python tests
python profiling/scripts/run_ui_bench.py
```

Live UI timing: `MAGNETAR_PROFILE_UI=1 magnetar` (see `profiling/README.md`).

## Skills (load these)

| When | Skill |
|------|--------|
| Theme keys, CSS-like chrome, styled widgets | project `/widget-theme` |
| Tests, ruff, env, how to run the app | project `/magnetar-dev` |
| GitHub issues / PRs / Actions via MCP | project `/github-mcp` |
| `git push`, `gh`, SSH, commit author | user `/github-auth` |
| Surgical Python edits | user `/edit-with-diff` |

## Conventions

- Ruff: line length **100**, target **py314** (`pyproject.toml`).
- Widget chrome lives in `python/magnetar/widgets/default_theme.py` (copyable class attrs). Resolve live with `theme_value` / `set_theme`. Do not re-hardcode cyan in `app._build_ui` for widget chrome.
- Prompt is fed from `HistoryTextEntry` on the main thread. Replies go to stdout and `Prompt.last_message`.
- `SDL_AUDIODRIVER=dummy` is intentional (do not “fix” it by opening a real mixer).
- Never commit `env314/`, `temp/`, `secrets/`, PATs, or MCP tokens.
- Confirm with the user before push, PR create/comment, or GitHub MCP write actions.

## MCP

GitHub MCP is **project-scoped** in `.grok/config.toml` (remote HTTP + OAuth).  
This folder must be trusted or the server will not start: `/hooks-trust` (same gate as hooks/LSP).  
Then `/mcps` → `r`, then `i` to sign in. Full setup: `docs/github-mcp.md`.

## Open work

See `TODO.md`. Do not invent a finished Coulomb/Maxwell core or a stdin TTY prompt — those are still open.

## Docs to read first

1. `README.md` — setup and run
2. `TODO.md` — current gaps
3. `.grok/skills/widget-theme/SKILL.md` — when touching theme
4. `profiling/README.md` — when touching draw cost
