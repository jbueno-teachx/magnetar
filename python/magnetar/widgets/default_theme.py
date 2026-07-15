# SPDX-License-Identifier: CC0-1.0
"""Default widget theme (cyan chrome) — copy this file to fork a theme.

This module is intentionally self-contained (no magnetar imports) so you can
duplicate it, edit the class attributes, and pass the class (or the module)
to ``set_theme``::

    # my_night_theme.py  (a copy of this file, values tweaked)
    class Theme:
        color = (180, 220, 255)
        ...

    from magnetar.widgets import set_theme
    import my_night_theme
    set_theme(my_night_theme.Theme)
    # or: set_theme(my_night_theme)  if you put attrs on the module instead

Attribute names follow common CSS where the concepts match
(``color``, ``background``, ``border``, ``padding``, …).
Values are class attributes only — no ``__init__`` required.
"""

from __future__ import annotations

from typing import Any

# RGB / RGBA tuples (pygame-friendly).
Color = tuple[int, int, int]
ColorA = tuple[int, int, int, int]


class Theme:
    """Default magnetar UI chrome (cyan accent, translucent panels, thin border)."""

    # --- CSS-like core -------------------------------------------------------
    color: Color = (0, 255, 255)  # primary text / accent (cyan)
    background: ColorA = (8, 16, 20, 200)  # translucent panel fill
    border: Color = (0, 255, 255)  # chrome edge
    border_width: int = 1
    border_radius: int = 3
    padding: int = 8

    # --- Focus / secondary text ----------------------------------------------
    border_focus: Color = (0, 255, 200)
    color_placeholder: Color = (0, 120, 120)
    color_caret: Color = (0, 255, 255)

    # --- Typography ----------------------------------------------------------
    # ``font`` is a pygame.font.Font once the app has initialized fonts;
    # ``None`` means widgets need an explicit font= or assign Theme.font.
    font: Any = None
    font_size: int = 18
    line_gap: int = 2

    # --- Variant fills -------------------------------------------------------
    background_button: ColorA = (20, 40, 40, 180)
    background_input: ColorA = (12, 24, 28, 220)
