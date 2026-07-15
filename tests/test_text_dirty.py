# SPDX-License-Identifier: CC0-1.0
"""TextWidget dirty flag and content equality for TextEntry / TextPanel."""

from magnetar.widgets import TextEntry, TextPanel, TextWidget


def test_textentry_equal_assign_no_dirty() -> None:
    e = TextEntry(0, 0, 50, 10, text="hello")
    assert e.dirty is True
    e.mark_clean()
    e.text = "hello"
    assert e.dirty is False
    assert e.content_key == "hello"
    e.text = "hello!"
    assert e.dirty is True
    assert e.text == "hello!"


def test_textentry_clear_idempotent() -> None:
    e = TextEntry(0, 0, 50, 10, text="")
    e.mark_clean()
    e.clear(notify=False)
    assert e.dirty is False


def test_textwidget_exported() -> None:
    assert issubclass(TextEntry, TextWidget)
    assert issubclass(TextPanel, TextWidget)
