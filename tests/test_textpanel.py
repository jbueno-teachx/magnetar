# SPDX-License-Identifier: CC0-1.0
"""TextPanel multi-line display widget."""

import pygame

from magnetar.widgets import EventInterest, TextPanel, WidgetPointerEvent, WidgetRegistry


def test_set_lines_and_write_grid() -> None:
    panel = TextPanel(0, 0, 50, 50)
    panel.set_lines(["hello", "world"])
    assert panel.lines == ["hello", "world"]

    panel.write(0, 5, "!")
    assert panel.lines[0] == "hello!"

    panel.write(2, 2, "x")
    assert panel.lines[2] == "  x"

    panel.write(0, 0, "ab\ncd")
    assert panel.lines[0].startswith("ab")
    assert panel.lines[1] == "cd" or panel.lines[1].startswith("cd")


def test_append_and_max_lines() -> None:
    panel = TextPanel(0, 0, 50, 50, max_lines=3)
    panel.append_line("a")
    panel.append_line("b")
    panel.append_line("c")
    panel.append_line("d")
    assert panel.lines == ["b", "c", "d"]


def test_write_rejects_negative() -> None:
    panel = TextPanel(0, 0, 10, 10)
    try:
        panel.write(-1, 0, "x")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_visible_slice_scroll_to_end() -> None:
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 20)
        panel = TextPanel(
            0,
            0,
            100,
            50,
            font=font,
            scroll_to_end=True,
            padding_px=4,
            line_gap_px=0,
        )
        panel.set_lines([f"L{i}" for i in range(20)])
        size = (200, 200)
        cap = panel.visible_line_capacity(size)
        assert cap >= 1
        visible = panel._visible_slice(size)
        assert len(visible) == min(cap, 20)
        assert visible[-1] == "L19"
        assert panel.interest is EventInterest.NONE
    finally:
        pygame.font.quit()


def test_draw_does_not_raise() -> None:
    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.Surface((320, 240))
        font = pygame.font.Font(None, 18)
        panel = TextPanel(
            1,
            1,
            50,
            30,
            font=font,
            border=(0, 255, 255),
            text_color=(0, 255, 255),
            closable=True,
        )
        panel.set_text("magnetar\nview ok")
        panel.draw(screen)
    finally:
        pygame.font.quit()
        pygame.display.quit()


def test_close_x_hides_panel() -> None:
    closed: list[str] = []
    panel = TextPanel(
        0,
        0,
        50,
        40,
        closable=True,
        on_close=lambda: closed.append("x"),
    )
    size = (200, 200)
    cr = panel.close_rect(size)
    assert panel.hit_test(cr.center, size)
    # Body of panel is not hit-tested (pass-through).
    body = panel.screen_rect(size).center
    if not cr.collidepoint(body):
        assert not panel.hit_test(body, size)

    pe = WidgetPointerEvent(kind="click", pos=cr.center, button=1)
    assert panel.on_event(pe, size) is True
    assert panel.visible is False
    assert closed == ["x"]


def test_show_reopens() -> None:
    panel = TextPanel(0, 0, 20, 20, closable=True)
    panel.hide()
    assert panel.visible is False
    panel.show()
    assert panel.visible is True


def test_app_hud_status_only_and_prompt_out() -> None:
    from magnetar.app import MagnetarApp

    app = MagnetarApp()
    pygame.display.init()
    pygame.font.init()
    try:
        app.font = pygame.font.Font(None, 18)
        from magnetar.widgets import get_theme

        get_theme().font = app.font
        app._build_ui()
        assert app._hud_panel is not None
        assert app._prompt_out is not None
        assert app._hud_panel.name == "hud"
        assert app._prompt_out.name == "prompt_out"
        assert app._prompt_out.closable is True
        assert app._prompt_out.visible is False

        app.draw_hud()
        lines = app._hud_panel.lines
        assert lines[0].startswith("magnetar")
        assert not any("added" in ln for ln in lines)

        app._append_prompt_output("added electro")
        assert app._prompt_out.visible is True
        assert any("added electro" in ln for ln in app._prompt_out.lines)
        # HUD unchanged by prompt output.
        assert not any("added electro" in ln for ln in app._hud_panel.lines)

        # Close via X then reopen on new output.
        size = (1024, 768)
        cr = app._prompt_out.close_rect(size)
        app._prompt_out.on_event(
            WidgetPointerEvent(kind="click", pos=cr.center, button=1),
            size,
        )
        assert app._prompt_out.visible is False
        app._append_prompt_output("cleared 1 particle(s)")
        assert app._prompt_out.visible is True
        assert any("cleared" in ln for ln in app._prompt_out.lines)

        # Geometry: prompt_out bottom aligns with prompt top band.
        assert app._prompt_entry is not None
        pout = app._prompt_out.screen_rect(size)
        prompt = app._prompt_entry.screen_rect(size)
        assert pout.bottom == prompt.top
        assert pout.left == prompt.left
    finally:
        pygame.display.quit()
        pygame.font.quit()


def test_registry_dispatches_close_click() -> None:
    pygame.display.init()
    try:
        reg = WidgetRegistry()
        panel = TextPanel(0, 0, 50, 50, closable=True, name="log")
        reg.add(panel)
        size = (200, 200)
        cr = panel.close_rect(size)
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=cr.center, button=1)
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, pos=cr.center, button=1)
        reg.dispatch(down, size)
        reg.dispatch(up, size)
        assert panel.visible is False
    finally:
        pygame.display.quit()


def test_set_lines_equal_is_noop_dirty() -> None:
    panel = TextPanel(0, 0, 20, 20)
    assert panel.set_lines(["a", "b"]) is True
    assert panel._dirty is True
    panel._dirty = False
    assert panel.set_lines(["a", "b"]) is False
    assert panel._dirty is False
    assert panel._content_key == ("a", "b")
    # draw_hud-style spam
    for _ in range(50):
        assert panel.set_lines(["a", "b"]) is False
    assert panel._dirty is False


def test_append_marks_dirty() -> None:
    panel = TextPanel(0, 0, 20, 20)
    panel._dirty = False
    assert panel.append_line("x") is True
    assert panel._dirty is True
