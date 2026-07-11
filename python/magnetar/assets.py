# SPDX-License-Identifier: CC0-1.0
"""Packaged assets: fonts, particle images, and path helpers."""

import os
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Iterable, Optional, Type

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

# ---------------------------------------------------------------------------
# Paths / sessions
# ---------------------------------------------------------------------------

# Relative to the ``magnetar`` package root.
HUD_FONT_RESOURCE = "assets/fonts/IBMPlexSans-Bold.ttf"
DEFAULT_HUD_FONT_SIZE = 18

PARTICLE_IMAGE_VARIANTS: tuple[str, ...] = (
    "yellow",
    "light_blue",
    "red",
    "green",
)
DEFAULT_PARTICLE_COLOR = "yellow"


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


# ---------------------------------------------------------------------------
# Particle image bank (load / cache — used by Particle, not App)
# ---------------------------------------------------------------------------

class ParticleImageBank:
    """Eager/lazy load + scale cache for particle PNGs under assets/particles/.

    Layout (current and reserved)::

        particle_{color}.png
        particle_{color}_f{NNN}.png
        particle_{color}_{tag}.png
        particle_{color}_{tag}_f{NNN}.png
        {color}/frame_{NNN}.png

    Particles call :meth:`shared` / :meth:`get` directly; the App does not own this.
    """

    _shared: ClassVar[ParticleImageBank | None] = None

    def __init__(self) -> None:
        self._masters: dict[tuple[str, int, str], pygame.Surface] = {}
        self._scaled: dict[tuple[str, int, str, int], pygame.Surface] = {}
        self._loaded_defaults = False

    @classmethod
    def shared(cls) -> ParticleImageBank:
        """Process-wide bank instance (safe to call from any Particle)."""
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @classmethod
    def reset_shared(cls) -> None:
        """Drop the singleton (tests / full reload)."""
        cls._shared = None

    def ensure_defaults(self, variants: Iterable[str] = PARTICLE_IMAGE_VARIANTS) -> None:
        """Eager-load still masters for the shipped color variants."""
        if self._loaded_defaults:
            return
        for variant in variants:
            self._ensure_master(variant, frame=0, tag=None)
        self._loaded_defaults = True

    def get(
        self,
        color: str,
        *,
        size_px: int,
        frame: int = 0,
        tag: str | None = None,
    ) -> pygame.Surface:
        """Return a sprite scaled to ``size_px`` × ``size_px`` (screen diameter)."""
        size_px = max(1, int(size_px))
        self.ensure_defaults()
        master = self._ensure_master(color, frame=frame, tag=tag)
        key = (color, frame, tag or "", size_px)
        cached = self._scaled.get(key)
        if cached is not None:
            return cached
        if master.get_width() == size_px and master.get_height() == size_px:
            scaled = master
        else:
            scaled = pygame.transform.smoothscale(master, (size_px, size_px))
        self._scaled[key] = scaled
        return scaled

    def _ensure_master(
        self,
        color: str,
        *,
        frame: int,
        tag: str | None,
    ) -> pygame.Surface:
        key = (color, frame, tag or "")
        if key in self._masters:
            return self._masters[key]

        rel = self._resolve_resource(color, frame=frame, tag=tag)
        with packaged_asset(*rel.split("/")) as path:
            # convert_alpha requires a display mode; fall back if headless.
            loaded = pygame.image.load(str(path))
            try:
                surface = loaded.convert_alpha()
            except pygame.error:
                surface = loaded
        self._masters[key] = surface
        return surface

    def _resolve_resource(
        self,
        color: str,
        *,
        frame: int,
        tag: str | None,
    ) -> str:
        candidates: list[str] = []
        if tag:
            candidates.append(f"assets/particles/particle_{color}_{tag}_f{frame:03d}.png")
            if frame == 0:
                candidates.append(f"assets/particles/particle_{color}_{tag}.png")
        candidates.append(f"assets/particles/particle_{color}_f{frame:03d}.png")
        candidates.append(f"assets/particles/{color}/frame_{frame:03d}.png")
        if frame == 0:
            candidates.append(f"assets/particles/particle_{color}.png")

        root = files("magnetar")
        for rel in candidates:
            node = root
            for part in rel.split("/"):
                node = node / part
            try:
                if node.is_file():
                    return rel
            except Exception:
                continue
        raise FileNotFoundError(
            f"no particle image for color={color!r} frame={frame} tag={tag!r}; "
            f"tried: {candidates}"
        )
