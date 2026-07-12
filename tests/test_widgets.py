# SPDX-License-Identifier: CC0-1.0
"""Widget framework and orbit-control helpers."""

import math

import pygame

from magnetar.widgets import (
    DragImageButton,
    EventInterest,
    Widget,
    WidgetRegistry,
    make_curved_arrows_icon,
)


def test_screen_rect_uses_percentages() -> None:
    w = Widget(10, 20, 25, 50, name="box")
    rect = w.screen_rect((200, 100))
    assert rect == pygame.Rect(20, 20, 50, 50)


def test_quadrant_at() -> None:
    rect = pygame.Rect(0, 0, 100, 100)
    assert DragImageButton.quadrant_at((80, 50), rect) == "right"
    assert DragImageButton.quadrant_at((20, 50), rect) == "left"
    assert DragImageButton.quadrant_at((50, 20), rect) == "up"
    assert DragImageButton.quadrant_at((50, 80), rect) == "down"


def test_zone_center_manhattan() -> None:
    rect = pygame.Rect(0, 0, 100, 100)
    # Dead center
    assert DragImageButton.zone_at((50, 50), rect) == "center"
    # Within 10% manhattan of center (nx+ny)
    assert DragImageButton.zone_at((52, 50), rect) == "center"
    # Outside center band → quadrant
    assert DragImageButton.zone_at((80, 50), rect) == "right"


def test_registry_mask_and_click_command() -> None:
    pygame.display.init()
    try:
        reg = WidgetRegistry()
        assert reg.interest_mask == EventInterest.NONE

        hits: list[str] = []
        img = make_curved_arrows_icon(32)
        btn = DragImageButton(0, 0, 50, 50, img, command=lambda q: hits.append(q), name="orb")
        reg.add(btn)
        assert EventInterest.CLICK in reg.interest_mask
        assert EventInterest.DRAG in reg.interest_mask

        size = (100, 100)
        # Click in right half of widget (widget is 0-50% of 100 → 0..50 px)
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(40, 25), button=1)
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(40, 25), button=1)
        assert reg.dispatch(down, size)
        assert reg.dispatch(up, size)
        assert hits == ["right"]
    finally:
        pygame.display.quit()


def test_registry_drag_capture_outside_widget() -> None:
    pygame.display.init()
    try:
        reg = WidgetRegistry()
        drags: list[tuple[int, int]] = []
        img = make_curved_arrows_icon(32)
        btn = DragImageButton(
            0,
            0,
            30,
            30,
            img,
            on_drag=lambda dx, dy, tx, ty: drags.append((dx, dy)),
            drag_threshold_px=1,
        )
        reg.add(btn)
        size = (100, 100)
        # Start inside (0..30 px)
        assert reg.dispatch(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(10, 10), button=1), size
        )
        # Move outside while held
        assert reg.dispatch(
            pygame.event.Event(pygame.MOUSEMOTION, pos=(90, 10), rel=(80, 0), buttons=(1, 0, 0)),
            size,
        )
        assert reg.dispatch(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(90, 10), button=1), size)
        assert drags  # at least one drag callback
        assert sum(d[0] for d in drags) != 0
    finally:
        pygame.display.quit()


def test_orbit_click_rotates_app_view() -> None:
    from magnetar.app import MagnetarApp
    from magnetar.view3d import IDENTITY_MAT3
    from magnetar.units import meters

    app = MagnetarApp()
    pygame.display.init()
    try:
        app._build_ui()
        assert app._orbit_button is not None
        app._on_orbit_click("right")
        # Camera-relative step: matrix leaves identity
        assert app.view_matrix != IDENTITY_MAT3
        # Looking at origin: camera offset unchanged
        assert app.camera_offset == (0.0, 0.0, 0.0)

        # Pure yaw swings Z out of pure depth — it must have on-screen length.
        (uz, vz), _ = app.project(meters(0, 0, 3))
        (u0, v0), _ = app.project(meters(0, 0, 0))
        assert math.hypot(uz - u0, vz - v0) > 10.0

        # Yaw + pitch: X and Z must not be collinear on screen.
        app._on_orbit_click("up")
        (ux, vx), _ = app.project(meters(3, 0, 0))
        (uz, vz), _ = app.project(meters(0, 0, 3))
        (u0, v0), _ = app.project(meters(0, 0, 0))
        dx_x, dy_x = ux - u0, vx - v0
        dx_z, dy_z = uz - u0, vz - v0
        cross = abs(dx_x * dy_z - dy_x * dx_z)
        assert cross > 1.0

        app._on_orbit_click("center")
        assert app.view_matrix == IDENTITY_MAT3
    finally:
        pygame.display.quit()


def test_orbit_is_incremental_from_current() -> None:
    """Two successive right-clicks should keep composing, not snap to fixed axes."""
    from magnetar.app import MagnetarApp

    app = MagnetarApp()
    app._on_orbit_click("right")
    m1 = app.view_matrix
    app._on_orbit_click("right")
    m2 = app.view_matrix
    assert m1 != m2
    app._on_orbit_click("up")
    m3 = app.view_matrix
    assert m3 != m2
