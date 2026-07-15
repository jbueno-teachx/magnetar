# SPDX-License-Identifier: CC0-1.0
"""TextWidget dirty flag and content equality for TextEntry / TextPanel."""

from magnetar.widgets import TextEntry, TextPanel, TextWidget


def test_textentry_equal_assign_no_dirty() -> None:
    e = TextEntry(0, 0, 50, 10, text="hello")
    assert e._dirty is True
    e._dirty = False
    e.text = "hello"
    assert e._dirty is False
    assert e._content_key == "hello"
    e.text = "hello!"
    assert e._dirty is True
    assert e.text == "hello!"


def test_textentry_clear_idempotent() -> None:
    e = TextEntry(0, 0, 50, 10, text="")
    e._dirty = False
    e.clear(notify=False)
    assert e._dirty is False


def test_textwidget_exported() -> None:
    assert issubclass(TextEntry, TextWidget)
    assert issubclass(TextPanel, TextWidget)
