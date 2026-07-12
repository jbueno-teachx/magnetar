# SPDX-License-Identifier: CC0-1.0
"""Widget framework and orbit-control helpers."""

import math

import pygame

from magnetar.widgets import (
    Anchor,
    AnchorH,
    AnchorV,
    DragImageButton,
    EventInterest,
    KeyEvent,
    TextEntry,
    WIDGET_CHANGED,
    WIDGET_FOCUS,
    WIDGET_SUBMIT,
    Widget,
    WidgetRegistry,
    make_curved_arrows_icon,
)


def test_screen_rect_uses_percentages() -> None:
    w = Widget(10, 20, 25, 50, name="box")
    rect = w.screen_rect((200, 100))
    assert rect == pygame.Rect(20, 20, 50, 50)


def test_screen_rect_anchor_bottom_right() -> None:
    # Anchor at (100%, 100%) bottom-right of a 40×20 box on a 200×100 screen.
    w = Widget(100, 100, 20, 20, anchor=Anchor(h="right", v="bottom"))
    rect = w.screen_rect((200, 100))
    assert rect.width == 40
    assert rect.height == 20
    assert rect.right == 200
    assert rect.bottom == 100


def test_anchor_parse_aliases() -> None:
    a = Anchor.parse("bottomleft")
    assert a.h is AnchorH.LEFT
    assert a.v is AnchorV.BOTTOM
    b = Anchor.parse(("right", "center"))
    assert b.h is AnchorH.RIGHT
    assert b.v is AnchorV.CENTER


def test_prompt_and_orbit_share_bottom_edge() -> None:
    from magnetar.app import MagnetarApp

    app = MagnetarApp()
    pygame.display.init()
    pygame.font.init()
    try:
        app.font = pygame.font.Font(None, 18)
        app._build_ui()
        size = (1024, 768)
        assert app._orbit_button is not None and app._prompt_entry is not None
        orbit = app._orbit_button.screen_rect(size)
        prompt = app._prompt_entry.screen_rect(size)
        assert orbit.bottom == prompt.bottom
        assert prompt.right <= orbit.left
    finally:
        pygame.display.quit()


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


def test_text_entry_typing_arrows_backspace_submit() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        pygame.event.clear()
        font = pygame.font.Font(None, 24)
        reg = WidgetRegistry()
        entry = TextEntry(0, 0, 100, 20, font=font, name="line")
        reg.add(entry)
        reg.set_focus(entry)
        size = (400, 40)

        def key(k: int, uni: str = "") -> pygame.event.Event:
            return pygame.event.Event(pygame.KEYDOWN, key=k, unicode=uni, mod=0)

        assert reg.dispatch(key(pygame.K_a, "a"), size)
        assert reg.dispatch(key(pygame.K_b, "b"), size)
        assert reg.dispatch(key(pygame.K_c, "c"), size)
        assert entry.text == "abc"
        assert entry.cursor == 3

        assert reg.dispatch(key(pygame.K_LEFT), size)
        assert entry.cursor == 2
        assert reg.dispatch(key(pygame.K_BACKSPACE), size)
        assert entry.text == "ac"
        assert entry.cursor == 1

        assert reg.dispatch(key(pygame.K_RIGHT), size)
        assert entry.cursor == 2

        # Drain focus/change noise, then submit.
        pygame.event.clear()
        assert reg.dispatch(key(pygame.K_RETURN), size)
        submitted = [e for e in pygame.event.get() if e.type == WIDGET_SUBMIT]
        assert len(submitted) == 1
        assert submitted[0].text == "ac"
        assert submitted[0].widget is entry
        assert submitted[0].name == "line"
    finally:
        pygame.display.quit()


def test_text_entry_length_limited_to_widget_width() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        # Narrow field in pixel space: 10% of 200px = 20px wide → almost no chars.
        entry = TextEntry(0, 0, 10, 50, font=font, padding_px=2)
        reg = WidgetRegistry()
        reg.add(entry)
        reg.set_focus(entry)
        size = (200, 40)
        for _ in range(40):
            reg.dispatch(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, unicode="M", mod=0),
                size,
            )
        assert entry.text
        assert font.size(entry.text)[0] <= entry.screen_rect(size).width - 2 * entry.padding_px
    finally:
        pygame.display.quit()


def test_text_entry_posts_generic_widget_events() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        pygame.event.clear()
        entry = TextEntry(0, 0, 50, 20, font=pygame.font.Font(None, 20))
        entry.focus()
        kinds = {e.type for e in pygame.event.get()}
        assert WIDGET_FOCUS in kinds

        pygame.event.clear()
        entry.handle_key(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, unicode="x", mod=0),
            (400, 40),
        )
        kinds = {e.type for e in pygame.event.get()}
        assert WIDGET_CHANGED in kinds
    finally:
        pygame.display.quit()


def test_app_builds_prompt_entry() -> None:
    from magnetar.app import MagnetarApp

    app = MagnetarApp()
    pygame.display.init()
    pygame.font.init()
    try:
        app.font = pygame.font.Font(None, 18)
        app._build_ui()
        assert app._prompt_entry is not None
        assert app._prompt_entry in list(app.widgets)
        assert app.widgets.focus is app._prompt_entry
    finally:
        pygame.display.quit()


def _keydown(key: int, uni: str = "", *, mod: int = 0) -> pygame.event.Event:
    """Synthetic KEYDOWN — same shape as SDL auto-repeat posts for a held key."""
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=uni, mod=mod)


def test_key_event_registry_case_insensitive() -> None:
    assert KeyEvent["HOME"] is KeyEvent["home"]
    assert KeyEvent["Kill_To_End"] is KeyEvent.mapping["kill_to_end"]
    assert KeyEvent["HOME"].match(_keydown(pygame.K_HOME))
    assert KeyEvent["HOME"].match(_keydown(pygame.K_a, mod=pygame.KMOD_CTRL))
    assert not KeyEvent["HOME"].match(_keydown(pygame.K_a, "a"))
    assert KeyEvent["KILL_TO_END"].match(_keydown(pygame.K_k, mod=pygame.KMOD_CTRL))
    # match any of several events
    e_miss = _keydown(pygame.K_z)
    e_hit = _keydown(pygame.K_LEFT)
    assert KeyEvent["BACKWARD_CHAR"].match(e_miss, e_hit)


def test_text_entry_autorepeat_char_via_repeated_keydown() -> None:
    """Held-key auto-repeat is modeled as successive KEYDOWN events (set_repeat)."""
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        reg = WidgetRegistry()
        entry = TextEntry(0, 0, 100, 30, font=font)
        reg.add(entry)
        reg.set_focus(entry)
        size = (800, 60)
        for _ in range(8):
            assert reg.dispatch(_keydown(pygame.K_x, "x"), size)
        assert entry.text == "xxxxxxxx"
        assert entry.cursor == 8
    finally:
        pygame.display.quit()


def test_text_entry_autorepeat_backspace_and_arrows() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        reg = WidgetRegistry()
        entry = TextEntry(0, 0, 100, 30, font=font, text="abcdef")
        entry.cursor = 6
        reg.add(entry)
        reg.set_focus(entry)
        size = (800, 60)

        for _ in range(3):
            assert reg.dispatch(_keydown(pygame.K_BACKSPACE), size)
        assert entry.text == "abc"
        assert entry.cursor == 3

        for _ in range(2):
            assert reg.dispatch(_keydown(pygame.K_LEFT), size)
        assert entry.cursor == 1

        for _ in range(5):
            assert reg.dispatch(_keydown(pygame.K_RIGHT), size)
        assert entry.cursor == 3  # clamped at end
    finally:
        pygame.display.quit()


def test_text_entry_delete_home_end() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        entry = TextEntry(0, 0, 100, 30, font=font, text="wxyz")
        entry.focus()
        entry.cursor = 1  # between w and x → Delete removes x
        size = (800, 60)
        assert entry.handle_key(_keydown(pygame.K_DELETE), size)
        assert entry.text == "wyz"
        assert entry.cursor == 1
        assert entry.handle_key(_keydown(pygame.K_END), size)
        assert entry.cursor == 3
        assert entry.handle_key(_keydown(pygame.K_HOME), size)
        assert entry.cursor == 0
    finally:
        pygame.display.quit()


def test_text_entry_ctrl_a_e_are_home_end() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="hello")
        entry.focus()
        entry.cursor = 2
        size = (800, 60)
        assert entry.handle_key(_keydown(pygame.K_a, mod=pygame.KMOD_CTRL), size)
        assert entry.cursor == 0
        assert entry.handle_key(_keydown(pygame.K_e, mod=pygame.KMOD_CTRL), size)
        assert entry.cursor == 5
        # Plain a still inserts (no Ctrl).
        assert entry.handle_key(_keydown(pygame.K_a, "a"), size)
        assert entry.text == "helloa"
    finally:
        pygame.display.quit()


def test_text_entry_emacs_movement_and_kill() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        entry = TextEntry(0, 0, 100, 30, font=font, text="foo bar baz")
        entry.focus()
        size = (900, 60)

        # Ctrl+B / Ctrl+F
        entry.cursor = 4
        assert entry.handle_key(_keydown(pygame.K_b, mod=pygame.KMOD_CTRL), size)
        assert entry.cursor == 3
        assert entry.handle_key(_keydown(pygame.K_f, mod=pygame.KMOD_CTRL), size)
        assert entry.cursor == 4

        # Alt+F / Alt+B word motion
        entry.cursor = 0
        assert entry.handle_key(_keydown(pygame.K_f, mod=pygame.KMOD_ALT), size)
        assert entry.cursor == 3  # after "foo"
        assert entry.handle_key(_keydown(pygame.K_f, mod=pygame.KMOD_ALT), size)
        assert entry.cursor == 7  # after "bar"
        assert entry.handle_key(_keydown(pygame.K_b, mod=pygame.KMOD_ALT), size)
        assert entry.cursor == 4  # start of "bar"

        # Ctrl+K kill to end, Ctrl+Y yank
        entry.cursor = 4
        assert entry.handle_key(_keydown(pygame.K_k, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "foo "
        assert entry._kill_buffer == "bar baz"
        assert entry.handle_key(_keydown(pygame.K_y, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "foo bar baz"

        # Ctrl+U kill to start
        entry.cursor = 4
        assert entry.handle_key(_keydown(pygame.K_u, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "bar baz"
        assert entry.cursor == 0

        # Ctrl+W kill word backward
        entry.text = "one two"
        entry.cursor = 7
        assert entry.handle_key(_keydown(pygame.K_w, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "one "
        assert entry._kill_buffer == "two"

        # Alt+D kill word forward
        entry.text = "one two"
        entry.cursor = 0
        assert entry.handle_key(_keydown(pygame.K_d, mod=pygame.KMOD_ALT), size)
        assert entry.text == " two"
        assert entry._kill_buffer == "one"

        # Ctrl+D delete char; Ctrl+H backspace
        entry.text = "ab"
        entry.cursor = 0
        assert entry.handle_key(_keydown(pygame.K_d, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "b"
        entry.cursor = 1
        assert entry.handle_key(_keydown(pygame.K_h, mod=pygame.KMOD_CTRL), size)
        assert entry.text == ""

        # Ctrl+T transpose
        entry.text = "ab"
        entry.cursor = 1
        assert entry.handle_key(_keydown(pygame.K_t, mod=pygame.KMOD_CTRL), size)
        assert entry.text == "ba"
        assert entry.cursor == 2
    finally:
        pygame.display.quit()


def test_text_entry_escape_blurs_and_registry_clears_focus() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        pygame.event.clear()
        reg = WidgetRegistry()
        entry = TextEntry(0, 0, 50, 20, font=pygame.font.Font(None, 20))
        reg.add(entry)
        reg.set_focus(entry)
        assert entry.focused
        assert reg.focus is entry
        assert reg.dispatch(_keydown(pygame.K_ESCAPE), (400, 40))
        assert not entry.focused
        assert reg.focus is None
    finally:
        pygame.display.quit()


def test_app_enables_key_repeat() -> None:
    from magnetar.app import KEY_REPEAT_DELAY_MS, KEY_REPEAT_INTERVAL_MS, MagnetarApp

    app = MagnetarApp()
    try:
        app._init_pygame()
        delay, interval = pygame.key.get_repeat()
        assert delay == KEY_REPEAT_DELAY_MS
        assert interval == KEY_REPEAT_INTERVAL_MS
    finally:
        app._shutdown_pygame()


def test_text_entry_shift_arrow_selects() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="abcdef")
        entry.focus()
        entry.cursor = 2
        size = (800, 60)
        assert entry.handle_key(_keydown(pygame.K_RIGHT, mod=pygame.KMOD_SHIFT), size)
        assert entry.handle_key(_keydown(pygame.K_RIGHT, mod=pygame.KMOD_SHIFT), size)
        assert entry.has_selection()
        assert entry.selection_range() == (2, 4)
        assert entry.selected_text() == "cd"
        # Plain move preserves selection; only relocates caret.
        assert entry.handle_key(_keydown(pygame.K_LEFT), size)
        assert entry.has_selection()
        assert entry.selection_range() == (2, 4)
        assert entry.cursor == 3
    finally:
        pygame.display.quit()


def test_text_entry_mouse_drag_selects() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        entry = TextEntry(0, 0, 100, 50, font=font, text="hello")
        reg = WidgetRegistry()
        reg.add(entry)
        size = (400, 100)

        # Screen rect is full width 0..400; pad 8
        # Index positions via font widths
        def x_for(i: int) -> int:
            return 8 + font.size(entry.text[:i])[0]

        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x_for(1), 20), button=1)
        assert reg.dispatch(down, size)
        drag = pygame.event.Event(
            pygame.MOUSEMOTION, pos=(x_for(4), 20), rel=(10, 0), buttons=(1, 0, 0)
        )
        assert reg.dispatch(drag, size)
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x_for(4), 20), button=1)
        assert reg.dispatch(up, size)
        assert entry.has_selection()
        a, b = entry.selection_range()
        assert entry.text[a:b] == "ell"
    finally:
        pygame.display.quit()


def test_text_entry_click_clears_selection() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        entry = TextEntry(0, 0, 100, 50, font=font, text="hello")
        entry.focus()
        entry._sel = (0, 5)
        entry.cursor = 5
        assert entry.has_selection()
        size = (400, 100)
        reg = WidgetRegistry()
        reg.add(entry)
        # Click without drag mid-field
        x = 8 + font.size("he")[0]
        assert reg.dispatch(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, 20), button=1), size)
        assert reg.dispatch(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x, 20), button=1), size)
        assert not entry.has_selection()
    finally:
        pygame.display.quit()


def test_text_entry_type_and_delete_replace_selection() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="abcdef")
        entry.focus()
        entry._sel = (1, 4)  # "bcd"
        entry.cursor = 4
        size = (800, 60)
        assert entry.handle_key(_keydown(pygame.K_x, "x"), size)
        assert entry.text == "axef"
        assert not entry.has_selection()

        entry._sel = (1, 3)  # "xe"
        entry.cursor = 3
        assert entry.handle_key(_keydown(pygame.K_BACKSPACE), size)
        assert entry.text == "af"
        assert not entry.has_selection()

        entry.text = "hello"
        entry._sel = (0, 2)
        entry.cursor = 2
        assert entry.handle_key(_keydown(pygame.K_DELETE), size)
        assert entry.text == "llo"
    finally:
        pygame.display.quit()


def test_text_entry_cut_selection_to_clipboard() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        entry = TextEntry(0, 0, 100, 30, font=pygame.font.Font(None, 24), text="hello")
        entry.focus()
        entry._sel = (1, 4)  # "ell"
        entry.cursor = 4
        size = (800, 60)
        store: dict[str, str] = {}

        def fake_set(s: str) -> None:
            store["t"] = s

        from unittest.mock import patch

        with patch("magnetar.widgets.textentry.set_text", side_effect=fake_set):
            assert entry.handle_key(_keydown(pygame.K_x, mod=pygame.KMOD_CTRL), size)
        assert store["t"] == "ell"
        assert entry.text == "ho"
        assert not entry.has_selection()
    finally:
        pygame.display.quit()
