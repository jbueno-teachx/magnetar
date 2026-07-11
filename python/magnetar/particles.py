# SPDX-License-Identifier: CC0-1.0
"""Particle types for the magnetar simulation."""

import os
import weakref
from typing import TYPE_CHECKING, Optional, Tuple

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.assets import (
    DEFAULT_PARTICLE_COLOR,
    PARTICLE_IMAGE_VARIANTS,
    ParticleImageBank,
)
from magnetar.units import (
    Coulomb,
    Gram,
    Meter,
    Position,
    Second,
    as_position,
    coulomb,
    gram,
    second,
)

if TYPE_CHECKING:
    from magnetar.world import World

Velocity3 = Tuple[float, float, float]
ZERO_VELOCITY: Velocity3 = (0.0, 0.0, 0.0)

DEFAULT_MASS: Gram = gram(1.0)
DEFAULT_CHARGE: Coulomb = coulomb(1.0)
DEFAULT_SCREEN_RADIUS_PX = 8


def _as_velocity(value: Velocity3 | Tuple[float, float, float]) -> Velocity3:
    return (float(value[0]), float(value[1]), float(value[2]))


def _normalize_color(color: str) -> str:
    name = str(color).strip().lower().replace(" ", "_")
    if name not in PARTICLE_IMAGE_VARIANTS:
        # Allow unknown names if assets exist; bank will FileNotFoundError if not.
        if not name:
            return DEFAULT_PARTICLE_COLOR
    return name


class ScreenSprite(pygame.sprite.Sprite):
    """Intermediate sprite layer: ``image`` + ``rect`` for ``Group.draw``.

    ``image`` is loaded via :class:`~magnetar.assets.ParticleImageBank` (not App).
    ``rect`` still needs World→App→view for 3D projection.
    """

    def _require_app(self):
        world = getattr(self, "world", None)
        if world is None:
            raise RuntimeError("sprite is not attached to a world")
        app = world.app
        if app is None:
            raise RuntimeError("world has no app bound (ContextVar empty)")
        return app

    def _project_center(self) -> tuple[float, float, float] | None:
        """Return ``(u, v, depth)`` or None if app/view is unavailable."""
        try:
            app = self._require_app()
        except RuntimeError:
            return None
        view = getattr(app, "view", None)
        if view is not None:
            (u, v), depth = view.project(self.position)  # type: ignore[attr-defined]
        elif hasattr(app, "project"):
            (u, v), depth = app.project(self.position)
        else:
            return None
        return (float(u), float(v), float(depth))

    @property
    def image(self) -> pygame.Surface:
        """Current frame surface for this particle's color (scaled to sim diameter)."""
        color = getattr(self, "color", DEFAULT_PARTICLE_COLOR)
        frame = int(getattr(self, "sprite_frame", 0) or 0)
        tag = getattr(self, "sprite_tag", None)
        try:
            app = self._require_app()
            radius = int(getattr(app, "particle_radius_px", DEFAULT_SCREEN_RADIUS_PX))
        except RuntimeError:
            radius = DEFAULT_SCREEN_RADIUS_PX
        size_px = max(1, radius * 2)
        bank = ParticleImageBank.shared()
        try:
            return bank.get(color, size_px=size_px, frame=frame, tag=tag)
        except FileNotFoundError:
            return pygame.Surface((size_px, size_px), pygame.SRCALPHA)

    @property
    def rect(self) -> pygame.Rect:
        """Axis-aligned screen box centered on the projected world position."""
        projected = self._project_center()
        if projected is None:
            return pygame.Rect(0, 0, 0, 0)
        u, v, _depth = projected
        try:
            app = self._require_app()
            radius = int(getattr(app, "particle_radius_px", DEFAULT_SCREEN_RADIUS_PX))
        except RuntimeError:
            radius = DEFAULT_SCREEN_RADIUS_PX
        return pygame.Rect(
            int(round(u)) - radius,
            int(round(v)) - radius,
            radius * 2,
            radius * 2,
        )

    def view_depth(self) -> float:
        """View-space z (larger = farther); used for painter layering."""
        projected = self._project_center()
        if projected is None:
            return 0.0
        return projected[2]


class Particle(ScreenSprite):
    """A particle in 3D space (also a pygame Sprite for group membership).

    ``color`` selects the packaged particle image variant (e.g. ``\"yellow\"``).
    """

    def __init__(
        self,
        position: Position | tuple[float, float, float],
        velocity: Velocity3 = ZERO_VELOCITY,
        mass: Gram | float = DEFAULT_MASS,
        pinned: bool = False,
        label: str = "",
        color: str = DEFAULT_PARTICLE_COLOR,
        *,
        world: World | None = None,
        sprite_frame: int = 0,
        sprite_tag: str | None = None,
    ) -> None:
        super().__init__()
        self.position = as_position(position)
        self.mass = gram(mass)
        self.label = label
        self.color = _normalize_color(color)
        self._pinned = bool(pinned)
        self._velocity = ZERO_VELOCITY if self._pinned else _as_velocity(velocity)
        self._world_ref: Optional[weakref.ReferenceType[World]] = (
            weakref.ref(world) if world is not None else None
        )
        self.sprite_frame = int(sprite_frame)
        self.sprite_tag = sprite_tag

    @property
    def world(self) -> World | None:
        ref = self._world_ref
        if ref is None:
            return None
        return ref()

    def attach_world(self, world: World) -> None:
        self._world_ref = weakref.ref(world)

    def detach_world(self) -> None:
        self._world_ref = None

    @property
    def pinned(self) -> bool:
        return self._pinned

    @pinned.setter
    def pinned(self, value: bool) -> None:
        self._pinned = bool(value)
        if self._pinned:
            self._velocity = ZERO_VELOCITY

    @property
    def velocity(self) -> Velocity3:
        return self._velocity

    @velocity.setter
    def velocity(self, value: Velocity3 | Tuple[float, float, float]) -> None:
        if self._pinned:
            raise ValueError("cannot change velocity of a pinned particle")
        self._velocity = _as_velocity(value)

    def integrate(self, dt: Second | float) -> None:
        if self._pinned:
            return
        dt_s = float(second(dt))
        if dt_s == 0.0:
            return
        x, y, z = self.position
        vx, vy, vz = self._velocity
        self.position = as_position(
            (float(x) + vx * dt_s, float(y) + vy * dt_s, float(z) + vz * dt_s)
        )

    @property
    def x(self) -> Meter:
        return self.position[0]

    @property
    def y(self) -> Meter:
        return self.position[1]

    @property
    def z(self) -> Meter:
        return self.position[2]


class ElectroParticle(Particle):
    """Charged particle. ``charge`` and ``color`` are set at construction."""

    def __init__(
        self,
        position: Position | tuple[float, float, float],
        velocity: Velocity3 = ZERO_VELOCITY,
        mass: Gram | float = DEFAULT_MASS,
        pinned: bool = False,
        charge: Coulomb | float = DEFAULT_CHARGE,
        label: str = "",
        color: str = DEFAULT_PARTICLE_COLOR,
        *,
        world: World | None = None,
        sprite_frame: int = 0,
        sprite_tag: str | None = None,
    ) -> None:
        super().__init__(
            position,
            velocity=velocity,
            mass=mass,
            pinned=pinned,
            label=label,
            color=color,
            world=world,
            sprite_frame=sprite_frame,
            sprite_tag=sprite_tag,
        )
        self.charge = coulomb(charge)
