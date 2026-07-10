# SPDX-License-Identifier: CC0-1.0
"""Access packaged static assets via :mod:`importlib.resources`."""

from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

# Relative to the ``magnetar`` package root.
HUD_FONT_RESOURCE = "assets/fonts/IBMPlexSans-Bold.ttf"
DEFAULT_HUD_FONT_SIZE = 18


def resource_path(*parts: str):
    """Return an importlib Traversable for a path under the magnetar package."""
    node = files("magnetar")
    for part in parts:
        node = node / part
    return node


def hud_font_resource():
    """Traversable for the bundled HUD typeface (IBM Plex Sans Bold)."""
    return files("magnetar").joinpath(*HUD_FONT_RESOURCE.split("/"))


class AssetSession:
    """Context manager yielding a real filesystem path to a packaged resource.

    Wraps :func:`importlib.resources.as_file` so zip/wheel installs still work.
    Prefer ``with packaged_asset(...) as path:`` / ``with hud_font_path() as path:``.
    """

    def __init__(self, *resource_parts: str) -> None:
        self._parts = resource_parts
        self._stack = ExitStack()
        self.path: Path | None = None

    def __enter__(self) -> Path:
        traversable = files("magnetar").joinpath(*self._parts)
        path = self._stack.enter_context(as_file(traversable))
        self.path = Path(path)
        return self.path

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self._stack.close()
        self.path = None


def packaged_asset(*resource_parts: str) -> AssetSession:
    """Context manager for an arbitrary path under the ``magnetar`` package."""
    return AssetSession(*resource_parts)


def hud_font_path() -> AssetSession:
    """Context manager for the default bold HUD font file path."""
    return AssetSession(*HUD_FONT_RESOURCE.split("/"))
