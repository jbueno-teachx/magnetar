# SPDX-License-Identifier: CC0-1.0
"""Command prompt dispatcher (in-window entry → world)."""

from __future__ import annotations

from magnetar.prompt import Prompt
from magnetar.units import meters
from magnetar.world import World


def test_help_and_list_to_stdout(capsys) -> None:
    world = World()
    p = Prompt(world)
    assert p.execute("help") is False
    out = capsys.readouterr().out
    assert "commands:" in out
    assert "list" in out

    world.add_particle(meters(1, 0, 0))
    assert p.execute("list") is False
    out = capsys.readouterr().out
    assert "particle" in out
    assert "1.000" in out


def test_add_and_clear(capsys) -> None:
    world = World()
    p = Prompt(world)
    assert p.execute("add electro 0 0 0 1 2") is False
    assert len(world) == 1
    out = capsys.readouterr().out
    assert "added" in out
    assert p.execute("clear") is False
    assert len(world) == 0


def test_quit_returns_true(capsys) -> None:
    p = Prompt(World())
    assert p.execute("quit") is True
    assert "bye" in capsys.readouterr().out


def test_empty_and_unknown(capsys) -> None:
    p = Prompt(World())
    assert p.execute("") is False
    assert p.execute("   ") is False
    assert capsys.readouterr().out == ""
    assert p.execute("nope") is False
    assert "unknown command" in capsys.readouterr().out
