---
name: widget-theme
description: >
  Extend magnetar widget theming: add theme attributes, wire widget draw/layout
  to resolve them, keep default_theme.py copyable, and test set_theme. Use when
  adding theme keys, CSS-like chrome, new styled widgets, or the user runs
  /widget-theme or asks to extend the theme system.
metadata:
  short-description: "Add or extend magnetar widget Theme fields"
---

# widget-theme — extend the magnetar UI theme

Project skill for **new theme features** (new keys, new consumers, new widgets
that should respect chrome). Themes are **any** Python object with attributes
(class / module / instance / properties). Defaults live in a **copyable** file.

## Design rules (do not break)

1. **Default look** = class attributes only in
   `python/magnetar/widgets/default_theme.py` (no `self.`, no `__init__` for
   values). That file must stay **self-contained** (no magnetar imports) so it
   can be copied and passed to `set_theme`.
2. **Active theme** = whatever `set_theme(obj)` installed; resolve with
   `getattr` via `theme_value(name, override, default)` in
   `python/magnetar/widgets/theme.py`.
3. **Live resolution**: widgets re-read the theme at draw/layout time so
   `@property` / descriptors on an instance theme animate or remote-exec hacks
   work. Do not snapshot theme values once in `__init__` unless documenting an
   intentional override.
4. **CSS-inspired names** where the concept matches: `color`, `background`,
   `border`, `border_width`, `border_radius`, `padding`. Prefer those over new
   magnetar-only names when equivalent.
5. **Per-widget override**: constructor arg `None` means “use theme”; non-None
   wins. Prefer CSS names; keep short-lived back-compat aliases only if needed.
6. **No Java-style dirty getters** for theme; plain attributes + `theme_value`.
7. **App** (`python/magnetar/app.py`) should not hardcode chrome colors for
   widgets; it may inject `get_theme().font = …` after font load and set layout
   only.

## Pre-marked checklist — files to open

Work top-to-bottom. Skip rows that do not apply to the change.

### Theme definition & registry (always for new keys)

| Path | What to do |
|------|------------|
| `python/magnetar/widgets/default_theme.py` | Add the new **class attribute** + short comment. Keep file copyable. |
| `python/magnetar/widgets/theme.py` | Usually no change unless registry API changes. Re-exports `Theme`. |
| `python/magnetar/widgets/__init__.py` | Export new public names only if the package surface needs them. |

### Shared text chrome (`TextWidget`)

| Path | Methods / hooks |
|------|-----------------|
| `python/magnetar/widgets/textbase.py` | `__init__` overrides; helpers `theme_color`, `theme_background`, `theme_border`, `theme_padding`, `theme_font`, `theme_border_width`, `theme_border_radius`. Add a helper here if **TextEntry and TextPanel** both need the new key. |

### Concrete widgets (use theme at draw/layout)

| Path | Methods / hooks to review |
|------|---------------------------|
| `python/magnetar/widgets/textentry.py` | `__init__` (override kwargs); `draw`; `_draw_plain`; `_draw_with_selection`; `_sel_colors`; `_content_width_budget`; caret/placeholder `theme_value("color_caret"…)`, `border_focus`, `background_input`. |
| `python/magnetar/widgets/textpanel.py` | `__init__`; `draw`; `_draw_close_x`; `line_height` (`line_gap`); padding/capacity helpers; `theme_background(key="background")`. |
| `python/magnetar/widgets/history_textentry.py` | Usually inherits TextEntry; only if new kwargs must be plumbed. |
| `python/magnetar/widgets/buttons.py` | `Button.draw`, `DragImageButton.draw`; `make_curved_arrows_icon` (default `color` from theme); `background_button`, `border*`. |
| `python/magnetar/widgets/base.py` | Rarely; only if theming becomes base-Widget-wide. |
| `python/magnetar/widgets/registry.py` | Not theme-related unless focus chrome appears later. |
| `python/magnetar/widgets/clipboard.py` / `history.py` / `keyevent.py` | No theme (I/O / input). |

### App wiring

| Path | What to do |
|------|------------|
| `python/magnetar/app.py` | `_init`: keep `get_theme().font = self.font`. `_build_ui`: do **not** re-hardcode theme colors for panels/prompt unless intentional override. Axis/particle colors may stay app-local (not widget theme) unless the feature explicitly unifies them. |

### Tests (always for new keys or new consumers)

| Path | What to do |
|------|------------|
| `tests/test_theme.py` | Assert default class attr; `set_theme` with a **class** and/or instance property; override beats theme; optional draw smoke. |
| `tests/test_textpanel.py` | If TextPanel paints with the new key. |
| `tests/test_widgets.py` | If TextEntry / buttons / layout use the new key. |
| `tests/test_history_textentry.py` | Only if HistoryTextEntry kwargs change. |

### Profiling (optional)

| Path | When |
|------|------|
| `profiling/scripts/run_ui_bench.py` | If draw cost may change; re-bench after big paint path changes. |
| `profiling/data/baselines/ui_bench_baseline.json` | Only when intentionally refreshing the baseline. |

## Procedure for a **new theme attribute**

Example: add `shadow_color` used by TextPanel chrome.

1. **Name it** — CSS-like if possible (`box_shadow` only if you must; prefer simple attrs).
2. **`default_theme.py`** — add class attribute + one-line comment and default value.
3. **Consumers** — for each widget that should use it:
   - optional constructor override (`shadow_color: … | None = None`);
   - at draw/layout: `theme_value("shadow_color", self.shadow_color, default)`.
   - Prefer a `TextWidget` helper if shared by text widgets.
4. **Do not** require custom themes to subclass `Theme`; document the attribute
   name so a bare class/module works.
5. **Tests** — at least:
   - default present on `Theme` / `DEFAULT_THEME`;
   - `set_theme(CustomClass)` changes resolved value;
   - per-widget override still wins when set.
6. **Run** `pytest tests/test_theme.py tests/test_widgets.py tests/test_textpanel.py -q`
   (or full `tests/` if broader).
7. **Summarize** which files changed and the new attribute’s meaning/default.

## Procedure for a **new styled widget**

1. Prefer subclassing `TextWidget` or `Widget` + `theme_value` / TextWidget helpers.
2. Defaults: all chrome kwargs `None` → theme; never bake cyan literals into
   draw code (hardcoded fallbacks in `theme_value(..., default=…)` are OK as
   last-resort safety only; prefer matching `default_theme.py`).
3. Add tests that draw with theme font set (`Theme.font = pygame.font.Font(None, 18)`).
4. Export from `widgets/__init__.py` if public.

## Procedure for a **forked theme file** (user content, not core)

1. Copy `python/magnetar/widgets/default_theme.py` → e.g. `my_theme.py` (in or out of package).
2. Edit class attributes only.
3. `set_theme(MyTheme)` or `set_theme(my_module)` before / when building UI.
4. App may still assign `.font` on the active theme object after pygame font init
   (`get_theme().font = font` works for classes and instances).

## Current theme keys (keep this list honest when you edit)

When you add a key, **append it here** in the same PR as the code change:

| Attribute | Used by (approx.) |
|-----------|-------------------|
| `color` | TextEntry, TextPanel, icon default |
| `background` | TextPanel fill |
| `background_input` | TextEntry fill |
| `background_button` | Button / DragImageButton |
| `border` | panels, entry, buttons |
| `border_width` | panels, entry, buttons |
| `border_radius` | panels, entry, buttons |
| `padding` | TextWidget text inset |
| `border_focus` | TextEntry focused border |
| `color_placeholder` | TextEntry placeholder |
| `color_caret` | TextEntry caret |
| `font` | text widgets (app injects) |
| `font_size` | documented; app may load font at this size |
| `line_gap` | TextPanel line spacing |

## Anti-patterns

- Putting default values only in widget constructors and not in `default_theme.py`
- Importing `app` or pygame heavily from `default_theme.py` (breaks copyability)
- Resolving theme once in `__init__` and never reading again (breaks live/remote theme edits)
- Reintroducing magnetar `THEME_COLOR` hardcoding in `_build_ui` for widget chrome
- Forgetting tests for `set_theme` with a **class** (not only instances)

## Quick verify

```bash
source env314/bin/activate
pytest tests/test_theme.py tests/test_textpanel.py tests/test_widgets.py -q
```

Optional live check: run magnetar, then `sys.remote_exec` / pdb attach and mutate
`get_theme().color` — next frame should recolor if the new key is read each draw.
