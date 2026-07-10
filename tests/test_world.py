# SPDX-License-Identifier: CC0-1.0
import pytest

from magnetar.particles import ElectroParticle, Particle
from magnetar.units import (
    Coulomb,
    Gram,
    Meter,
    Position,
    Second,
    Tesla,
    Volt,
    coulomb,
    gram,
    grams_to_kg,
    meter,
    meters,
    second,
    tesla,
    volt,
)
from magnetar.world import World


def test_add_electro_and_step() -> None:
    world = World()
    p = world.add_electro(
        meters(0.0, 0.0, 0.0),
        charge=coulomb(1.0),
        mass=gram(2.0),
        velocity=(1.0, 0.0, 0.0),  # m/s
    )
    assert isinstance(p, ElectroParticle)
    assert p.charge == coulomb(1.0)
    assert p.mass == gram(2.0)
    assert p.position == meters(0.0, 0.0, 0.0)
    assert p.pinned is False
    assert p.world is world
    assert len(world) == 1
    world.step(second(0.5))
    assert world.particles[0].position == meters(0.5, 0.0, 0.0)
    assert world.time == second(0.5)


def test_pinned_particle_does_not_move() -> None:
    world = World()
    pos = meters(1.0, 2.0, 3.0)
    p = world.add_electro(
        pos,
        charge=coulomb(-2.0),
        mass=gram(1.0),
        velocity=(10.0, 10.0, 10.0),  # ignored because pinned
        pinned=True,
    )
    assert p.pinned
    assert p.position == pos
    assert p.velocity == (0.0, 0.0, 0.0)
    world.step(second(1.0))
    assert p.position == pos
    assert p.velocity == (0.0, 0.0, 0.0)


def test_pinned_velocity_assignment_raises() -> None:
    p = Particle(meters(0, 0, 0), velocity=(1, 0, 0), pinned=True)
    assert p.velocity == (0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="pinned"):
        p.velocity = (1.0, 0.0, 0.0)


def test_setting_pinned_zeroes_velocity() -> None:
    p = Particle(meters(0, 0, 0), velocity=(3.0, 4.0, 0.0))
    assert p.velocity == (3.0, 4.0, 0.0)
    p.pinned = True
    assert p.velocity == (0.0, 0.0, 0.0)
    # position remains writable while pinned
    p.position = meters(9.0, 8.0, 7.0)
    assert p.position == meters(9.0, 8.0, 7.0)


def test_weakref_to_world() -> None:
    world = World()
    p = world.add_particle(meters(0, 1, 0), mass=gram(3.5))
    assert p.world is world
    world.clear()
    assert p.world is None
    assert len(world) == 0


def test_base_particle_has_mass() -> None:
    world = World()
    p = world.add_particle(meters(0.0, 1.0, 0.0), mass=gram(3.5))
    assert isinstance(p, Particle)
    assert not isinstance(p, ElectroParticle)
    assert p.mass == gram(3.5)
    assert grams_to_kg(p.mass) == 0.0035
    assert p.y == meter(1.0)


def test_unit_constructors() -> None:
    t: Second = second(1.5)
    d: Meter = meter(2.0)
    pos: Position = meters(1, 2, 3)
    b: Tesla = tesla(0.5)
    q: Coulomb = coulomb(-1.6e-19)
    m: Gram = gram(1.0)
    v: Volt = volt(12.0)
    assert float(t) == 1.5
    assert float(d) == 2.0
    assert pos == (meter(1), meter(2), meter(3))
    assert float(b) == 0.5
    assert float(q) == -1.6e-19
    assert float(m) == 1.0
    assert float(v) == 12.0


def test_project_origin_is_center() -> None:
    from magnetar.app import VIEW_HEIGHT, VIEW_WIDTH, MagnetarApp

    app = MagnetarApp()
    (u, v), depth = app.project(meters(0.0, 0.0, 0.0), width=VIEW_WIDTH, height=VIEW_HEIGHT)
    assert u == VIEW_WIDTH * 0.5
    assert v == VIEW_HEIGHT * 0.5
    assert depth == 0.0
