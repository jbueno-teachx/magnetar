# SPDX-License-Identifier: CC0-1.0
from importlib.resources import files

from magnetar.assets import HUD_FONT_RESOURCE, hud_font_session


def test_hud_font_is_packaged() -> None:
    resource = files("magnetar").joinpath(*HUD_FONT_RESOURCE.split("/"))
    assert resource.is_file()
    data = resource.read_bytes()
    # TrueType magic
    assert data[0:4] == b"\x00\x01\x00\x00" or data[0:4] == b"true"


def test_hud_font_session_path() -> None:
    with hud_font_session() as path:
        assert path.is_file()
        assert path.suffix.lower() == ".ttf"
        assert path.stat().st_size > 10_000
