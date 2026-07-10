# SPDX-License-Identifier: CC0-1.0
"""3D simulation space holding particles."""

import contextvars
import os
from typing import TYPE_CHECKING, Any, Iterable, Optional

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.particles import (
    DEFAULT_CHARGE,
    DEFAULT_MASS,
    ElectroParticle,
    Particle,
    Velocity3,
)
from magnetar.units import Coulomb, Gram, Position, Second, as_position, coulomb, gram, second

if TYPE_CHECKING:
    pass


class World:
    """Container for particles living in continuous 3D space (meters, seconds).

    Particles are stored in a :class:`pygame.sprite.Group`. A per-instance
    :class:`contextvars.ContextVar` holds a reference to the owning app
    (set by :class:`~magnetar.app.MagnetarApp`).
    """

    def __init__(self) -> None:
        # Instance attribute (intentionally not a module-level ContextVar).
        self.app_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
            f"magnetar_app_{id(self)}",
            default=None,
        )
        self.particles: pygame.sprite.Group = pygame.sprite.Group()
        self.time: Second = second(0.0)

    # -- app binding (ContextVar instance attribute) --------------------------

    @property
    def app(self) -> Any | None:
        """The MagnetarApp bound to this world, if any."""
        return self.app_var.get()

    def bind_app(self, app: Any) -> contextvars.Token:
        """Store ``app`` in this world's instance ContextVar."""
        return self.app_var.set(app)

    def unbind_app(self) -> None:
        """Clear the app binding (sets the ContextVar default of None)."""
        self.app_var.set(None)

    # -- particle group -------------------------------------------------------

    def add(self, particle: Particle) -> Particle:
        """Attach ``particle`` to this world and add it to the sprite group."""
        particle.attach_world(self)
        self.particles.add(particle)
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
                label=label or f"P{len(self.particles)}",
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
            label=label or f"E{len(self.particles)}",
        )
        self.add(particle)
        return particle

    def remove(self, particle: Particle) -> None:
        """Detach and :meth:`~pygame.sprite.Sprite.kill` a particle."""
        particle.detach_world()
        particle.kill()

    def clear(self) -> None:
        """Remove every particle via :meth:`kill` and detach world refs."""
        for particle in list(self.particles):
            if isinstance(particle, Particle):
                particle.detach_world()
            particle.kill()
        # Belt-and-suspenders: ensure the group is empty.
        self.particles.empty()

    def step(self, dt: Second | float) -> None:
        """Advance the world by ``dt`` seconds (kinematics only for now)."""
        dt_s = second(dt)
        if dt_s <= 0:
            return
        for particle in self.particles:
            if isinstance(particle, Particle):
                particle.integrate(dt_s)
        self.time = second(float(self.time) + float(dt_s))

    def __iter__(self) -> Iterable[pygame.sprite.Sprite]:
        return iter(self.particles)

    def __len__(self) -> int:
        return len(self.particles)
