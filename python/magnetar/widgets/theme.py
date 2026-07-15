# SPDX-License-Identifier: CC0-1.0
"""Widget theme registry: active theme + resolution helpers.

The default look lives in :mod:`magnetar.widgets.default_theme` as a plain
class-attribute config (copy that file to fork a theme). This module only
tracks which object is active and resolves values with ``getattr``.

Call :func:`set_theme` with anything that exposes the theme field names:

* a class (class attributes — config-file style),
* a module,
* an instance (including ones with ``@property`` / descriptors).
"""

from __future__ import annotations

from typing import Any

from magnetar.widgets.default_theme import Color, ColorA, Theme

# Default theme is the class itself (class attrs). set_theme(None) restores this.
DEFAULT_THEME: Any = Theme
_active_theme: Any = DEFAULT_THEME


def get_theme() -> Any:
    """Return the active theme (class, module, or instance)."""
    return _active_theme


def set_theme(theme: Any) -> None:
    """Install ``theme`` as the active widget theme.

    Accepts any object that supports ``getattr`` for the theme field names:
    a class, a module, an instance, etc. Descriptors and ``@property`` on
    instances are resolved normally by :func:`theme_value`.

    Pass ``None`` to restore :data:`DEFAULT_THEME`
    (:class:`~magnetar.widgets.default_theme.Theme`).
    """
    global _active_theme
    _active_theme = DEFAULT_THEME if theme is None else theme


def theme_value(name: str, override: Any = None, default: Any = None) -> Any:
    """Resolve ``override`` if set, else ``getattr(active_theme, name, default)``.

    Works for class attributes, instance attributes, modules, and properties.
    """
    if override is not None:
        return override
    return getattr(get_theme(), name, default)


__all__ = [
    "Color",
    "ColorA",
    "DEFAULT_THEME",
    "Theme",
    "get_theme",
    "set_theme",
    "theme_value",
]
