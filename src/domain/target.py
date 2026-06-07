"""What is currently 'in front' — the thing BTN_MODE acts on.

A small sum type replacing the old ``{'type': 'app'|'dyn', 'id', 'name', ...}``
context dict and its stringly-typed ``ctx['type']`` branching. Pure Python.
"""

from dataclasses import dataclass

from .app import TRIGGER_CLICK


@dataclass(frozen=True)
class AppTarget:
    """A configured app tile, identified by its index in the app list."""

    index: int
    name:  str


@dataclass(frozen=True)
class WindowTarget:
    """An externally-launched window tile, identified by its KWin window id.

    Carries the recall trigger inherited from the owning app (e.g. a game
    launched by Steam inherits Steam's BTN_MODE_HOLD_1S).
    """

    window_id: str
    name:      str
    trigger:   str = TRIGGER_CLICK


# A foreground target is either a configured app or an external window.
Target = AppTarget | WindowTarget
