# SPDX-License-Identifier: CC0-1.0
"""Access packaged static assets via :mod:`importlib.resources`."""

from __future__ import annotations

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


class AssetFontSession:
    """Keep a packaged font file available as a real filesystem path.

    Wraps :func:`importlib.resources.as_file` so zip/egg installs still work.
    Use as a context manager, or call :meth:`open` / :meth:`close` for app lifetime.
    """

    def __init__(self, *resource_parts: str) -> None:
        self._parts = resource_parts
        self._stack = ExitStack()
        self.path: Path | None = None

    def open(self) -> Path:
        if self.path is not None:
            return self.path
        traversable = files("magnetar").joinpath(*self._parts)
        path = self._stack.enter_context(as_file(traversable))
        self.path = Path(path)
        return self.path

    def close(self) -> None:
        self._stack.close()
        self.path = None

    def __enter__(self) -> Path:
        return self.open()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()


def hud_font_session() -> AssetFontSession:
    """Session for the default bold HUD font baked into the package."""
    return AssetFontSession(*HUD_FONT_RESOURCE.split("/"))
