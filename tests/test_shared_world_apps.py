# SPDX-License-Identifier: CC0-1.0
"""Can one World be viewed by different apps (scale / rotation)?

Current design: ``World.app_var`` is a *single* ContextVar instance attribute.
In one execution context only one app is "current" at a time (last ``bind_app``
wins). Sequential rebinding works. True simultaneous multi-view needs either
separate ``contextvars.Context``s or an explicit app argument to projection.
"""

import contextvars
import math
from dataclasses import dataclass
from typing import Sequence, Tuple


from magnetar.units import meters
from magnetar.world import World


Vec2 = Tuple[float, float]
Vec3f = Tuple[float, float, float]


@dataclass
class MockApp:
    """Minimal stand-in for MagnetarApp — only what Particle.rect / project need."""

    world_scale: float = 80.0
    world_rotation: Vec3f = (0.0, 0.0, 0.0)
    camera_offset: Vec3f = (0.0, 0.0, 0.0)
    perspective: float = 0.08
    particle_radius_px: int = 8
    width: int = 1024
    height: int = 768
    name: str = "mock"

    def __post_init__(self) -> None:
        # ScreenSprite.rect looks up app.view.project (or app.project).
        self.view = self

    def project(
        self,
        point: Sequence[float],
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> Tuple[Vec2, float]:
        w = self.width if width is None else width
        h = self.height if height is None else height
        ox, oy, oz = self.camera_offset
        x = float(point[0]) - ox
        y = float(point[1]) - oy
        z = float(point[2]) - oz
        x, y, z = _rotate(x, y, z, self.world_rotation)
        factor = 1.0 / max(0.2, 1.0 + z * self.perspective)
        u = w * 0.5 + x * self.world_scale * factor
        v = h * 0.5 - y * self.world_scale * factor
        return (u, v), z


def _rotate(x: float, y: float, z: float, rotation: Sequence[float]) -> Vec3f:
    yaw, pitch, roll = (float(rotation[0]), float(rotation[1]), float(rotation[2]))
    if yaw == 0.0 and pitch == 0.0 and roll == 0.0:
        return (x, y, z)
    if roll != 0.0:
        cr, sr = math.cos(roll), math.sin(roll)
        y, z = y * cr - z * sr, y * sr + z * cr
    if pitch != 0.0:
        cp, sp = math.cos(pitch), math.sin(pitch)
        x, z = x * cp + z * sp, -x * sp + z * cp
    if yaw != 0.0:
        cy, sy = math.cos(yaw), math.sin(yaw)
        x, y = x * cy - y * sy, x * sy + y * cy
    return (x, y, z)


def test_same_world_rebound_to_apps_with_different_scale() -> None:
    """One World can be referenced by app A then app B; rect follows each scale."""
    world = World()
    particle = world.add_particle(meters(1.0, 0.0, 0.0))

    app_small = MockApp(world_scale=40.0, name="small")
    app_large = MockApp(world_scale=160.0, name="large")

    world.bind_app(app_small)
    assert world.app is app_small
    rect_small = particle.rect

    world.bind_app(app_large)
    assert world.app is app_large
    rect_large = particle.rect

    # Same world-space point; larger scale → farther from screen center in u.
    center_u = app_small.width * 0.5
    assert rect_small.centerx != rect_large.centerx
    assert abs(rect_large.centerx - center_u) > abs(rect_small.centerx - center_u)
    # Particle still belongs to the single shared world / group.
    assert particle.world is world
    assert particle in world.particles


def test_same_world_rebound_with_different_rotation() -> None:
    world = World()
    particle = world.add_particle(meters(1.0, 0.0, 0.0))

    app_id = MockApp(world_rotation=(0.0, 0.0, 0.0), name="id")
    app_yaw = MockApp(world_rotation=(math.pi / 2, 0.0, 0.0), name="yaw90")

    world.bind_app(app_id)
    (u0, v0), _ = app_id.project(particle.position)
    rect0 = particle.rect

    world.bind_app(app_yaw)
    (u1, v1), _ = app_yaw.project(particle.position)
    rect1 = particle.rect

    assert (u0, v0) != (u1, v1)
    assert (rect0.centerx, rect0.centery) != (rect1.centerx, rect1.centery)
    # rect centers track project() of the *currently bound* app
    assert rect1.centerx == int(round(u1))
    assert rect1.centery == int(round(v1))


def test_same_context_last_bind_wins_not_simultaneous() -> None:
    """In one context, two apps cannot both be world.app at once."""
    world = World()
    particle = world.add_particle(meters(1.0, 0.0, 0.0))
    app_a = MockApp(world_scale=40.0, name="a")
    app_b = MockApp(world_scale=160.0, name="b")

    world.bind_app(app_a)
    world.bind_app(app_b)

    assert world.app is app_b
    assert world.app is not app_a
    # rect always uses the single current binding
    (u_b, _), _ = app_b.project(particle.position)
    assert particle.rect.centerx == int(round(u_b))


def test_bind_app_token_restores_previous_app() -> None:
    world = World()
    particle = world.add_particle(meters(1.0, 0.0, 0.0))
    app_a = MockApp(world_scale=40.0, name="a")
    app_b = MockApp(world_scale=160.0, name="b")

    world.bind_app(app_a)
    token = world.bind_app(app_b)
    assert world.app is app_b

    world.app_var.reset(token)
    assert world.app is app_a
    (u_a, _), _ = app_a.project(particle.position)
    assert particle.rect.centerx == int(round(u_a))


def test_isolated_contexts_allow_different_apps_on_same_world() -> None:
    """The ContextVar *can* hold different apps in different Contexts.

    This is how one World supports concurrent views without rebinding in the
    same stack: each viewer runs inside its own ``contextvars.Context``.
    """
    world = World()
    particle = world.add_particle(meters(1.0, 0.0, 0.0))
    app_a = MockApp(world_scale=40.0, name="a")
    app_b = MockApp(world_scale=160.0, name="b")

    def view_with(app: MockApp) -> tuple[int, object]:
        world.bind_app(app)
        r = particle.rect
        return r.centerx, world.app

    ctx_a = contextvars.Context()
    ctx_b = contextvars.Context()

    u_a, bound_a = ctx_a.run(view_with, app_a)
    u_b, bound_b = ctx_b.run(view_with, app_b)

    assert bound_a is app_a
    assert bound_b is app_b
    assert u_a != u_b
    # Parent / default context was never bound by those Context runs.
    assert world.app is None


def test_two_magnetar_apps_sharing_world_factory_last_wins() -> None:
    """Two MagnetarApp instances with a shared World overwrite each other's bind."""
    from magnetar.app import MagnetarApp

    shared = World()
    shared.add_particle(meters(1.0, 0.0, 0.0))

    def factory() -> World:
        return shared

    app1 = MagnetarApp(world_factory=factory)
    app1.world_scale = 40.0
    app2 = MagnetarApp(world_factory=factory)
    app2.world_scale = 160.0

    assert app1.world is app2.world is shared
    # Second constructor's bind_app replaced the first.
    assert shared.app is app2
    assert shared.app is not app1
