# SPDX-License-Identifier: CC0-1.0
"""Widget theme: set_theme / default resolution."""

from types import SimpleNamespace

import pygame

from magnetar.widgets import (
    DEFAULT_THEME,
    TextEntry,
    TextPanel,
    Theme,
    get_theme,
    set_theme,
)


def setup_function() -> None:
    set_theme(None)
    # Class-level font may be left set by other tests.
    Theme.font = None


def teardown_function() -> None:
    set_theme(None)
    Theme.font = None


def test_default_theme_is_the_class() -> None:
    assert get_theme() is DEFAULT_THEME
    assert get_theme() is Theme
    assert get_theme().color == (0, 255, 255)
    assert get_theme().border_width == 1
    assert get_theme().padding == 8


def test_set_theme_class_attrs() -> None:
    """Config-file style: pass a class with class attributes."""

    class Purple:
        color = (128, 0, 128)
        background = (20, 0, 20, 200)
        border = (255, 0, 255)
        border_width = 2
        border_radius = 0
        padding = 4
        font = None
        background_input = (30, 0, 30, 220)
        border_focus = (200, 100, 255)
        color_placeholder = (80, 40, 80)
        color_caret = (255, 0, 255)
        line_gap = 1
        background_button = (40, 0, 40, 180)

    set_theme(Purple)  # class, not instance
    assert get_theme() is Purple
    panel = TextPanel(0, 0, 50, 50)
    assert panel.theme_color() == (128, 0, 128)
    assert panel.theme_padding() == 4
    assert panel.theme_border_width() == 2


def test_set_theme_subclass_of_theme() -> None:
    class Night(Theme):
        color = (180, 220, 255)
        background = (4, 8, 16, 220)

    set_theme(Night)
    assert get_theme().color == (180, 220, 255)
    # Unoverridden names still come from Theme MRO
    assert get_theme().padding == Theme.padding


def test_set_theme_module_like_namespace() -> None:
    ns = SimpleNamespace(
        color=(1, 2, 3),
        background=Theme.background,
        border=Theme.border,
        border_width=1,
        border_radius=3,
        padding=9,
        font=None,
        background_input=Theme.background_input,
        border_focus=Theme.border_focus,
        color_placeholder=Theme.color_placeholder,
        color_caret=Theme.color_caret,
        line_gap=2,
        background_button=Theme.background_button,
    )
    set_theme(ns)
    assert TextPanel(0, 0, 10, 10).theme_color() == (1, 2, 3)
    assert TextPanel(0, 0, 10, 10).theme_padding() == 9


def test_instance_override_beats_theme() -> None:
    set_theme(None)
    panel = TextPanel(0, 0, 50, 50, color=(255, 0, 0), padding=12)
    assert panel.theme_color() == (255, 0, 0)
    assert panel.theme_padding() == 12
    assert panel.theme_border() == Theme.border


def test_theme_property_can_animate() -> None:
    class Pulse:
        def __init__(self) -> None:
            self._t = 0

        @property
        def color(self):
            return (self._t % 256, 255, 255)

        background = Theme.background
        border = Theme.border
        border_width = 1
        border_radius = 3
        padding = 8
        font = None
        background_input = Theme.background_input
        border_focus = Theme.border_focus
        color_placeholder = Theme.color_placeholder
        color_caret = Theme.color_caret
        line_gap = 2
        background_button = Theme.background_button

    pulse = Pulse()
    set_theme(pulse)
    entry = TextEntry(0, 0, 50, 20)
    assert entry.theme_color() == (0, 255, 255)
    pulse._t = 100
    assert entry.theme_color() == (100, 255, 255)


def test_draw_uses_theme_without_explicit_colors() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 18)
        Theme.font = font  # class attr assignment is fine
        screen = pygame.Surface((200, 100))
        panel = TextPanel(0, 0, 50, 50)
        panel.set_lines(["hi"])
        panel.draw(screen)
        entry = TextEntry(0, 50, 50, 20, text="x")
        entry.draw(screen)
    finally:
        Theme.font = None
        pygame.font.quit()
        pygame.display.quit()
