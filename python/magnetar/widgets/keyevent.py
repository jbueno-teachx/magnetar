# SPDX-License-Identifier: CC0-1.0
"""Named key bindings (Emacs / readline style)."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


class _ModSentinel:
    """Modifier marker used in :class:`KeyEvent` combo tuples."""

    __slots__ = ("name", "masks")

    def __init__(self, name: str, *masks: int) -> None:
        self.name = name
        self.masks = masks

    def present(self, mod: int) -> bool:
        return any(mod & m for m in self.masks)

    def __repr__(self) -> str:
        return f"KeyEvent.{self.name.upper()}"


class KeyEvent:
    """Named logical key action with one or more physical combos.

    Instantiation registers the binding in :attr:`mapping` (case-insensitive
    names). Lookup: ``KeyEvent["HOME"]`` / ``KeyEvent["home"]``.

    Combo forms (varargs to the constructor)::

        pygame.K_HOME                 # bare key
        "A"                           # letter key (case-insensitive)
        (KeyEvent.CTRL, "K")          # modifier + key
        (KeyEvent.ALT, pygame.K_BACKSPACE)

    Matching::

        if KeyEvent["HOME"].match(event):
            ...
        KeyEvent["HOME"].match(e1, e2)  # True if *any* event matches
    """

    # Modifier sentinels for combo tuples
    CTRL = _ModSentinel("ctrl", pygame.KMOD_CTRL)
    CONTROL = CTRL  # alias
    ALT = _ModSentinel("alt", pygame.KMOD_ALT)
    META = _ModSentinel("meta", pygame.KMOD_META, pygame.KMOD_GUI)
    SHIFT = _ModSentinel("shift", pygame.KMOD_SHIFT)

    # name.casefold() -> instance
    mapping: dict[str, "KeyEvent"] = {}

    # Bits treated as "chord modifiers" when a combo specifies none.
    _CHORD_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI

    def __init__(self, name: str, *combos: Any) -> None:
        if not name or not str(name).strip():
            raise ValueError("KeyEvent name must be non-empty")
        if not combos:
            raise ValueError(f"KeyEvent {name!r} needs at least one combo")
        self.name = str(name)
        self.combos: list[tuple[Any, ...]] = []
        for combo in combos:
            if isinstance(combo, tuple):
                if not combo:
                    raise ValueError(f"KeyEvent {name!r}: empty combo")
                self.combos.append(combo)
            else:
                # Bare key constant or letter string.
                self.combos.append((combo,))
        KeyEvent.mapping[self.name.casefold()] = self

    def __repr__(self) -> str:
        return f"KeyEvent({self.name!r}, …)"

    @classmethod
    def __class_getitem__(cls, name: str) -> "KeyEvent":
        try:
            return cls.mapping[str(name).casefold()]
        except KeyError as exc:
            raise KeyError(f"unknown KeyEvent {name!r}") from exc

    @classmethod
    def get(cls, name: str, default: "KeyEvent | None" = None) -> "KeyEvent | None":
        return cls.mapping.get(str(name).casefold(), default)

    @staticmethod
    def _token_to_key(token: Any) -> int | None:
        if isinstance(token, _ModSentinel):
            return None
        if isinstance(token, int):
            return int(token)
        if isinstance(token, str) and len(token) == 1:
            ch = token.lower()
            attr = f"K_{ch}"
            if hasattr(pygame, attr):
                return int(getattr(pygame, attr))
            # Digits and a few symbols via K_0 … if present
            return None
        if isinstance(token, str) and token.startswith("K_"):
            return int(getattr(pygame, token))
        return None

    def _match_combo(self, event: pygame.event.Event, combo: tuple[Any, ...]) -> bool:
        if getattr(event, "type", None) != pygame.KEYDOWN:
            return False
        mods = int(getattr(event, "mod", 0) or 0)
        required: list[_ModSentinel] = []
        key_code: int | None = None
        for part in combo:
            if isinstance(part, _ModSentinel):
                required.append(part)
                continue
            key_code = self._token_to_key(part)
            if key_code is None:
                return False
        if key_code is None or int(event.key) != key_code:
            return False
        for sentinel in required:
            if not sentinel.present(mods):
                return False
        if not required and (mods & self._CHORD_MODS):
            # Bare keys must not be part of a Ctrl/Alt/Meta chord.
            return False
        # When mods are required, still ignore if an *unrelated* chord family
        # is held without being listed (Ctrl vs Alt). Shift alone is fine.
        need_ctrl = any(s is KeyEvent.CTRL or s is KeyEvent.CONTROL for s in required)
        need_alt = any(s is KeyEvent.ALT for s in required)
        need_meta = any(s is KeyEvent.META for s in required)
        need_shift = any(s is KeyEvent.SHIFT for s in required)
        if required:
            if (mods & pygame.KMOD_CTRL) and not need_ctrl:
                return False
            # Alt without ALT/META in the combo is a different chord.
            if (mods & pygame.KMOD_ALT) and not need_alt and not need_meta:
                return False
            if (mods & (pygame.KMOD_META | pygame.KMOD_GUI)) and not need_meta and not need_alt:
                return False
            # Shift is optional unless the combo lists SHIFT (Ctrl+C still matches
            # Ctrl+Shift+C when only CTRL is required).
            if need_shift and not (mods & pygame.KMOD_SHIFT):
                return False
        return True

    def match(self, event: pygame.event.Event, *more: pygame.event.Event) -> bool:
        """Return True if any of the given pygame events matches this binding."""
        for ev in (event, *more):
            for combo in self.combos:
                if self._match_combo(ev, combo):
                    return True
        return False


# Logical bindings used by :class:`TextEntry` (and available app-wide).
KeyEvent("BACKWARD_CHAR", pygame.K_LEFT, (KeyEvent.CTRL, "B"))
KeyEvent("FORWARD_CHAR", pygame.K_RIGHT, (KeyEvent.CTRL, "F"))
KeyEvent("BACKWARD_WORD", (KeyEvent.ALT, "B"), (KeyEvent.META, "B"))
KeyEvent("FORWARD_WORD", (KeyEvent.ALT, "F"), (KeyEvent.META, "F"))
KeyEvent("HOME", pygame.K_HOME, (KeyEvent.CTRL, "A"))
KeyEvent("END", pygame.K_END, (KeyEvent.CTRL, "E"))
KeyEvent("BACKSPACE", pygame.K_BACKSPACE, (KeyEvent.CTRL, "H"))
KeyEvent("DELETE_CHAR", pygame.K_DELETE, (KeyEvent.CTRL, "D"))
KeyEvent("KILL_TO_END", (KeyEvent.CTRL, "K"))
KeyEvent("KILL_TO_START", (KeyEvent.CTRL, "U"))
KeyEvent(
    "KILL_WORD_BACKWARD",
    (KeyEvent.CTRL, "W"),
    (KeyEvent.ALT, pygame.K_BACKSPACE),
    (KeyEvent.META, pygame.K_BACKSPACE),
)
KeyEvent("KILL_WORD_FORWARD", (KeyEvent.ALT, "D"), (KeyEvent.META, "D"))
KeyEvent("YANK", (KeyEvent.CTRL, "Y"))
KeyEvent("TRANSPOSE", (KeyEvent.CTRL, "T"))
# System clipboard (full field until selection exists): Ctrl/Cmd+C, Ctrl+Shift+C.
KeyEvent(
    "COPY",
    (KeyEvent.CTRL, "C"),
    (KeyEvent.CTRL, KeyEvent.SHIFT, "C"),
    (KeyEvent.META, "C"),
)
KeyEvent(
    "CUT",
    (KeyEvent.CTRL, "X"),
    (KeyEvent.META, "X"),
)
KeyEvent(
    "PASTE",
    (KeyEvent.CTRL, "V"),
    (KeyEvent.META, "V"),
    (KeyEvent.SHIFT, pygame.K_INSERT),
)
KeyEvent("SUBMIT", pygame.K_RETURN, pygame.K_KP_ENTER)
KeyEvent("BLUR", pygame.K_ESCAPE)
# HistoryTextEntry navigation / reverse search
KeyEvent("HISTORY_UP", pygame.K_UP)
KeyEvent("HISTORY_DOWN", pygame.K_DOWN)
KeyEvent("HISTORY_SEARCH", (KeyEvent.CTRL, "R"))
