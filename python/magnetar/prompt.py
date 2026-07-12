# SPDX-License-Identifier: CC0-1.0
"""Simulation command dispatcher (input from the in-window text entry).

Commands are executed on the main thread. Replies and errors go to stdout.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass, field
from typing import Callable

from magnetar.particles import ElectroParticle
from magnetar.units import coulomb, gram, meters
from magnetar.world import World


@dataclass
class PromptCommand:
    """A parsed command line."""

    raw: str
    tokens: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.tokens[0].lower() if self.tokens else ""

    @property
    def args(self) -> list[str]:
        return self.tokens[1:]


class Prompt:
    """Parse and run commands against a :class:`~magnetar.world.World`.

    No stdin reader and no background thread — the app feeds lines from the
    UI (e.g. :class:`~magnetar.widgets.HistoryTextEntry` on Enter).
    """

    def __init__(self, world: World) -> None:
        self.world = world
        self._handlers: dict[str, Callable[[PromptCommand], str | None]] = {
            "help": self._cmd_help,
            "?": self._cmd_help,
            "list": self._cmd_list,
            "ls": self._cmd_list,
            "clear": self._cmd_clear,
            "add": self._cmd_add,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
            "q": self._cmd_quit,
        }

    def execute(self, line: str) -> bool:
        """Run one line. Return True if the application should quit."""
        line = str(line).strip()
        if not line:
            return False
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self._emit(f"parse error: {exc}")
            return False
        if not tokens:
            return False
        cmd = PromptCommand(raw=line, tokens=tokens)
        reply = self._dispatch(cmd)
        if reply is not None and reply != "":
            self._emit(reply)
        return cmd.name in {"quit", "exit", "q"}

    def _dispatch(self, cmd: PromptCommand) -> str | None:
        handler = self._handlers.get(cmd.name)
        if handler is None:
            return f"unknown command: {cmd.name!r} (try 'help')"
        try:
            return handler(cmd)
        except Exception as exc:  # noqa: BLE001 — surface errors to the user
            return f"error: {exc}"

    def _cmd_help(self, _cmd: PromptCommand) -> str:
        return (
            "commands:\n"
            "  help                               show this help\n"
            "  list                               list particles\n"
            "  add electro x y z [q] [mass_g]     free charged particle\n"
            "  add pinned x y z [q] [mass_g]      fixed charged source\n"
            "  add particle x y z [mass_g]        neutral particle\n"
            "  clear                              remove all particles\n"
            "  quit                               exit magnetar\n"
            "units: pos m, time s, charge C, mass g, B T, potential V"
        )

    def _cmd_list(self, _cmd: PromptCommand) -> str:
        if not self.world.particles:
            return "(no particles)"
        lines = []
        for i, p in enumerate(self.world.particles):
            x, y, z = (float(c) for c in p.position)
            kind = "electro" if isinstance(p, ElectroParticle) else "particle"
            charge = f" q={float(p.charge):g}C" if isinstance(p, ElectroParticle) else ""
            mass = f" m={float(p.mass):g}g"
            pinned = " pinned" if p.pinned else ""
            lines.append(
                f"  [{i}] {kind:8s} pos=({x:.3f}, {y:.3f}, {z:.3f})m"
                f"{charge}{mass}{pinned} {p.label}"
            )
        return "\n".join(lines)

    def _cmd_clear(self, _cmd: PromptCommand) -> str:
        n = len(self.world)
        self.world.clear()
        return f"cleared {n} particle(s)"

    def _cmd_add(self, cmd: PromptCommand) -> str:
        if len(cmd.args) < 4:
            return "usage: add electro|pinned|particle x y z [charge_C] [mass_g]"
        kind = cmd.args[0].lower()
        try:
            x, y, z = (float(cmd.args[1]), float(cmd.args[2]), float(cmd.args[3]))
        except ValueError:
            return "coordinates must be numbers"
        pos = meters(x, y, z)

        if kind in {"particle", "p", "neutral"}:
            try:
                mass = gram(cmd.args[4]) if len(cmd.args) > 4 else gram(1.0)
            except ValueError:
                return "mass must be a number (grams)"
            p = self.world.add_particle(pos, mass=mass)
            return f"added particle {p.label} m={float(p.mass):g}g at ({x:g}, {y:g}, {z:g})m"

        if kind in {"electro", "e", "electric", "pinned", "pin", "fixed", "bound"}:
            try:
                charge = coulomb(cmd.args[4]) if len(cmd.args) > 4 else coulomb(1.0)
                mass = gram(cmd.args[5]) if len(cmd.args) > 5 else gram(1.0)
            except ValueError:
                return "charge (C) and mass (g) must be numbers"
            pinned = kind in {"pinned", "pin", "fixed", "bound"}
            p = self.world.add_electro(pos, charge=charge, mass=mass, pinned=pinned)
            tag = "pinned electro" if p.pinned else "electro"
            return (
                f"added {tag} {p.label} q={float(p.charge):g}C "
                f"m={float(p.mass):g}g at ({x:g}, {y:g}, {z:g})m"
            )

        return f"unknown type: {kind!r} (try electro, pinned, or particle)"

    def _cmd_quit(self, _cmd: PromptCommand) -> str:
        return "bye"

    @staticmethod
    def _emit(text: str) -> None:
        try:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
            sys.stdout.flush()
        except Exception:
            pass


# Back-compat alias (old name used in early docs / imports).
InteractivePrompt = Prompt
