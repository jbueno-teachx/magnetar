"""Interactive stdin prompt for controlling the simulation space."""

from __future__ import annotations

import select
import shlex
import sys
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Callable, List, Optional

from magnetar.particles import ElectroParticle
from magnetar.units import coulomb, gram, meters
from magnetar.world import World

# Sentinel meaning "shut the app down" (EOF, quit command, or external stop).
_QUIT = object()


@dataclass
class PromptCommand:
    """A parsed line from the interactive prompt."""

    raw: str
    tokens: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.tokens[0].lower() if self.tokens else ""

    @property
    def args(self) -> List[str]:
        return self.tokens[1:]


class InteractivePrompt:
    """Background reader that feeds commands into a queue for the main loop."""

    def __init__(self, world: World, *, prompt: str = "magnetar> ") -> None:
        self.world = world
        self.prompt_text = prompt
        self._queue: Queue[object] = Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._handlers: dict[str, Callable[[PromptCommand], str]] = {
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

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader,
            name="magnetar-prompt",
            daemon=True,
        )
        self._thread.start()
        self._write(
            "Interactive prompt ready. Type 'help' for commands.\n"
            f"{self.prompt_text}"
        )

    def stop(self) -> None:
        """Signal the reader to exit and wait briefly for it."""
        self._stop.set()
        # Unblock poll waiters if any.
        self._queue.put(_QUIT)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)
        self._thread = None

    def request_quit(self) -> None:
        """Ask the main loop to shut down (from outside the prompt)."""
        self._queue.put(_QUIT)

    def poll(self) -> Optional[bool]:
        """Process pending commands.

        Returns
        -------
        None
            No quit requested.
        False
            Caller should shut down the application.
        """
        quit_requested = False
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is _QUIT or item is None:
                quit_requested = True
                continue
            if not isinstance(item, PromptCommand):
                continue
            reply = self._dispatch(item)
            if reply is not None:
                self._write(reply + "\n" + self.prompt_text)
            if item.name in {"quit", "exit", "q"}:
                quit_requested = True
        return False if quit_requested else None

    def _reader(self) -> None:
        """Read lines without blocking forever so stop()/window-close can finish."""
        stdin = sys.stdin
        # select works on the stdin fd (Unix). Fall back to blocking readline otherwise.
        use_select = hasattr(stdin, "fileno")
        if use_select:
            try:
                stdin.fileno()
            except (OSError, ValueError):
                use_select = False

        while not self._stop.is_set():
            try:
                if use_select:
                    ready, _, _ = select.select([stdin], [], [], 0.2)
                    if self._stop.is_set():
                        break
                    if not ready:
                        continue
                line = stdin.readline()
            except Exception:
                self._queue.put(_QUIT)
                break

            if line == "":
                # EOF (Ctrl+D)
                self._write("\n")
                self._queue.put(_QUIT)
                break

            line = line.strip()
            if not line:
                self._write(self.prompt_text)
                continue
            try:
                tokens = shlex.split(line)
            except ValueError as exc:
                self._write(f"parse error: {exc}\n{self.prompt_text}")
                continue
            self._queue.put(PromptCommand(raw=line, tokens=tokens))

    def _dispatch(self, cmd: PromptCommand) -> Optional[str]:
        handler = self._handlers.get(cmd.name)
        if handler is None:
            return f"unknown command: {cmd.name!r} (try 'help')"
        try:
            return handler(cmd)
        except Exception as exc:  # noqa: BLE001 — surface errors to the prompt
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
            return (
                f"added particle {p.label} m={float(p.mass):g}g "
                f"at ({x:g}, {y:g}, {z:g})m"
            )

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
    def _write(text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass
