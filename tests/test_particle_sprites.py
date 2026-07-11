# SPDX-License-Identifier: CC0-1.0
import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.assets import PARTICLE_IMAGE_VARIANTS, ParticleImageBank
from magnetar.particles import ElectroParticle, Particle
from magnetar.units import coulomb, gram, meters


def test_image_bank_load_and_scale() -> None:
    pygame.display.init()
    try:
        pygame.display.set_mode((64, 64))
        ParticleImageBank.reset_shared()
        bank = ParticleImageBank.shared()
        bank.ensure_defaults()
        for color in PARTICLE_IMAGE_VARIANTS:
            small = bank.get(color, size_px=16)
            assert small.get_size() == (16, 16)
    finally:
        ParticleImageBank.reset_shared()
        pygame.quit()


def test_particle_color_at_construction() -> None:
    p = ElectroParticle(meters(0, 0, 0), charge=coulomb(-1), color="light_blue")
    assert p.color == "light_blue"
    assert p.charge == coulomb(-1)
    n = Particle(meters(0, 0, 0), color="green", mass=gram(1))
    assert n.color == "green"
