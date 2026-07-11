# SPDX-License-Identifier: CC0-1.0
import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from magnetar.app import MagnetarApp, PARTICLE_RADIUS_PX
from magnetar.assets import ParticleImageBank
from magnetar.particles import ScreenSprite


def test_group_draw_uses_image_and_rect() -> None:
    pygame.display.init()
    try:
        screen = pygame.display.set_mode((128, 128))
        ParticleImageBank.reset_shared()
        app = MagnetarApp()
        app.screen = screen
        app.view.viewport_size = screen.get_size()

        p = next(iter(app.world.particles))
        assert isinstance(p, ScreenSprite)
        img = p.image
        r = p.rect
        assert isinstance(img, pygame.Surface)
        assert img.get_size() == (PARTICLE_RADIUS_PX * 2, PARTICLE_RADIUS_PX * 2)
        assert isinstance(r, pygame.Rect)
        assert r.width == PARTICLE_RADIUS_PX * 2

        screen.fill((0, 0, 0))
        app.world.particles.draw(screen)
    finally:
        ParticleImageBank.reset_shared()
        pygame.quit()


def test_rect_is_property_not_method() -> None:
    pygame.display.init()
    try:
        pygame.display.set_mode((64, 64))
        ParticleImageBank.reset_shared()
        app = MagnetarApp()
        p = next(iter(app.world.particles))
        assert not callable(p.rect)
        assert isinstance(p.rect, pygame.Rect)
    finally:
        ParticleImageBank.reset_shared()
        pygame.quit()
