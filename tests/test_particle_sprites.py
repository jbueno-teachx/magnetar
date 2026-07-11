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


def test_frame_count_yellow_is_eight() -> None:
    pygame.display.init()
    try:
        pygame.display.set_mode((32, 32))
        ParticleImageBank.reset_shared()
        bank = ParticleImageBank.shared()
        assert bank.frame_count("yellow") == 8
    finally:
        ParticleImageBank.reset_shared()
        pygame.quit()


def test_frame_index_wraps_with_tick() -> None:
    """Ticks are slowed by TICKS_PER_SPRITE_FRAME, then wrapped mod N frames."""
    from magnetar.particles import TICKS_PER_SPRITE_FRAME

    n_frames = 8
    tpf = TICKS_PER_SPRITE_FRAME  # 5
    assert tpf == 5
    assert (0 // tpf) % n_frames == 0
    assert (4 // tpf) % n_frames == 0  # still frame 0
    assert (5 // tpf) % n_frames == 1  # first advance
    assert ((8 * tpf) // tpf) % n_frames == 0  # full cycle wrap
