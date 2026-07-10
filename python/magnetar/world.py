"""3D simulation space holding particles."""

from __future__ import annotations

from typing import Iterable, List

from magnetar.particles import (
    DEFAULT_CHARGE,
    DEFAULT_MASS,
    ElectroParticle,
    Particle,
    Velocity3,
)
from magnetar.units import Coulomb, Gram, Position, Second, as_position, coulomb, gram, second


class World:
    """Container for particles living in continuous 3D space (meters, seconds)."""

    def __init__(self) -> None:
        self._particles: List[Particle] = []
        self.time: Second = second(0.0)

    @property
    def particles(self) -> List[Particle]:
        return self._particles

    def add(self, particle: Particle) -> Particle:
        particle.attach_world(self)
        self._particles.append(particle)
        return particle

    def add_particle(
        self,
        position: Position | tuple[float, float, float],
        *,
        velocity: Velocity3 = (0.0, 0.0, 0.0),
        mass: Gram | float = DEFAULT_MASS,
        pinned: bool = False,
        label: str = "",
    ) -> Particle:
        return self.add(
            Particle(
                as_position(position),
                velocity=velocity,
                mass=gram(mass),
                pinned=pinned,
                label=label or f"P{len(self._particles)}",
            )
        )

    def add_electro(
        self,
        position: Position | tuple[float, float, float],
        *,
        charge: Coulomb | float = DEFAULT_CHARGE,
        mass: Gram | float = DEFAULT_MASS,
        velocity: Velocity3 = (0.0, 0.0, 0.0),
        pinned: bool = False,
        label: str = "",
    ) -> ElectroParticle:
        particle = ElectroParticle(
            as_position(position),
            velocity=velocity,
            mass=gram(mass),
            pinned=pinned,
            charge=coulomb(charge),
            label=label or f"E{len(self._particles)}",
        )
        self.add(particle)
        return particle

    def clear(self) -> None:
        for p in self._particles:
            p.detach_world()
        self._particles.clear()

    def step(self, dt: Second | float) -> None:
        """Advance the world by ``dt`` seconds (kinematics only for now)."""
        dt_s = second(dt)
        if dt_s <= 0:
            return
        for p in self._particles:
            p.integrate(dt_s)
        self.time = second(float(self.time) + float(dt_s))

    def __iter__(self) -> Iterable[Particle]:
        return iter(self._particles)

    def __len__(self) -> int:
        return len(self._particles)
