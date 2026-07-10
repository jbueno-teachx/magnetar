# SPDX-License-Identifier: CC0-1.0
"""Particle types for the magnetar simulation."""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

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

# Velocity components are m/s (meters per second); kept as plain floats for now.
Velocity3 = Tuple[float, float, float]
ZERO_VELOCITY: Velocity3 = (0.0, 0.0, 0.0)

# Defaults for sandbox demos (not meant to match real particles).
DEFAULT_MASS: Gram = gram(1.0)
DEFAULT_CHARGE: Coulomb = coulomb(1.0)


def _as_velocity(value: Velocity3 | Tuple[float, float, float]) -> Velocity3:
    return (float(value[0]), float(value[1]), float(value[2]))


@dataclass
class Particle:
    """A particle in 3D space.

    ``position`` is in meters and remains writable even when pinned. If
    ``pinned`` is true, the particle does not integrate motion and only
    contributes to fields; attempts to assign ``velocity`` raise
    ``ValueError``. Setting ``pinned = True`` zeroes velocity immediately.
    """

    position: Position
    mass: Gram = DEFAULT_MASS
    label: str = ""
    # Display color override (RGB 0–255); None → theme default in the view.
    color: Tuple[int, int, int] | None = field(default=None)
    _velocity: Velocity3 = field(default=ZERO_VELOCITY, repr=False, compare=True)
    _pinned: bool = field(default=False, repr=False, compare=True)
    _world_ref: Optional[weakref.ReferenceType[World]] = field(
        default=None, repr=False, compare=False, hash=False
    )

    # Public constructor aliases (dataclass field names stay private).
    # Use keywords: Particle(pos, velocity=..., pinned=...)

    def __init__(
        self,
        position: Position | tuple[float, float, float],
        velocity: Velocity3 = ZERO_VELOCITY,
        mass: Gram | float = DEFAULT_MASS,
        pinned: bool = False,
        label: str = "",
        color: Tuple[int, int, int] | None = None,
        *,
        world: World | None = None,
    ) -> None:
        self.position = as_position(position)
        self.mass = gram(mass)
        self.label = label
        self.color = color
        self._pinned = bool(pinned)
        self._velocity = ZERO_VELOCITY if self._pinned else _as_velocity(velocity)
        self._world_ref = weakref.ref(world) if world is not None else None

    # -- world back-reference -------------------------------------------------

    @property
    def world(self) -> World | None:
        """The :class:`~magnetar.world.World` this particle belongs to, if any."""
        ref = self._world_ref
        if ref is None:
            return None
        return ref()

    def attach_world(self, world: World) -> None:
        """Record a weak reference to ``world`` (called by :meth:`World.add`)."""
        self._world_ref = weakref.ref(world)

    def detach_world(self) -> None:
        self._world_ref = None

    # -- pinned / velocity ----------------------------------------------------

    @property
    def pinned(self) -> bool:
        """If true, particle is fixed for dynamics (fields only)."""
        return self._pinned

    @pinned.setter
    def pinned(self, value: bool) -> None:
        self._pinned = bool(value)
        if self._pinned:
            self._velocity = ZERO_VELOCITY

    @property
    def velocity(self) -> Velocity3:
        """Velocity in m/s. Assignment is forbidden while pinned."""
        return self._velocity

    @velocity.setter
    def velocity(self, value: Velocity3 | Tuple[float, float, float]) -> None:
        if self._pinned:
            raise ValueError("cannot change velocity of a pinned particle")
        self._velocity = _as_velocity(value)

    # -- kinematics -----------------------------------------------------------

    def integrate(self, dt: Second | float) -> None:
        """Advance ``position`` by ``velocity * dt``. No-op when pinned."""
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


@dataclass
class ElectroParticle(Particle):
    """Charged particle. Responds to electric and magnetic fields when free."""

    charge: Coulomb = DEFAULT_CHARGE

    def __init__(
        self,
        position: Position | tuple[float, float, float],
        velocity: Velocity3 = ZERO_VELOCITY,
        mass: Gram | float = DEFAULT_MASS,
        pinned: bool = False,
        charge: Coulomb | float = DEFAULT_CHARGE,
        label: str = "",
        color: Tuple[int, int, int] | None = None,
        *,
        world: World | None = None,
    ) -> None:
        super().__init__(
            position,
            velocity=velocity,
            mass=mass,
            pinned=pinned,
            label=label,
            color=color,
            world=world,
        )
        self.charge = coulomb(charge)
