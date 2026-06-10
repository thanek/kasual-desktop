"""What is currently 'in front' — the thing BTN_MODE acts on.

A small sum type replacing the old ``{'type': 'app'|'dyn', 'id', 'name', ...}``
context dict and its stringly-typed ``ctx['type']`` branching. Pure Python.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .app import App, TRIGGER_CLICK
from .window import Window


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


def target_at_index(
    index:       int,
    apps:        Sequence[App],
    windows:     Sequence[Window],
    trigger_for: Callable[[int], str],
) -> Target | None:
    """The foreground Target at tile position *index*, or None if out of range.

    Tile layout is the configured apps first, then the open external windows: an
    index inside the app range is that ``AppTarget``; beyond it, the external
    window at that offset becomes a ``WindowTarget`` carrying the recall trigger
    it inherits (``trigger_for`` resolves a window's pid to its trigger — the
    parent-chain walk and /proc read behind it stay in infrastructure)."""
    if index < len(apps):
        return AppTarget(index=index, name=apps[index].name)
    window = windows[index - len(apps)] if index - len(apps) < len(windows) else None
    if window is None:
        return None
    return WindowTarget(window_id=window.id, name=window.title, trigger=trigger_for(window.pid))
