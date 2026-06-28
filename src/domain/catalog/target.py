"""What is currently 'in front' — the thing BTN_MODE acts on.

A small sum type replacing the old ``{'type': 'app'|'dyn', 'id', 'name', ...}``
context dict and its stringly-typed ``ctx['type']`` branching. Pure Python.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .app import App
from .window import Window
from ..input.vocabulary import Trigger


@dataclass(frozen=True)
class AppTarget:
    """A configured app tile, identified by its index in the app list.

    ``is_game`` carries the tile's ``Categories=Game`` flag so the Home Overlay
    can offer the HUD toggle for a game tile's own window (see
    :mod:`domain.system.hud`)."""

    index:   int
    name:    str
    is_game: bool = False


@dataclass(frozen=True)
class AddTileTarget:
    """The synthetic ``[＋]`` "Add app" tile that closes the pinned section.

    Not a real app or window: it carries no app index and no window id, so it has
    no lifecycle (never launches/restores/closes) and no management menu —
    activating it opens the add-app picker instead. A distinct type so the tile
    bar, the menu composer and the focus model can early-return for it rather than
    pattern-match a sentinel index."""


@dataclass(frozen=True)
class WindowTarget:
    """An externally-launched window tile, identified by its KWin window id.

    Carries the recall trigger inherited from the owning app (e.g. a game
    launched by Steam inherits Steam's BTN_MODE_HOLD_1S) and the owning OS pid,
    passed to the platform ``is_game_pid`` predicate to decide whether the HUD
    toggle should be offered (see :func:`domain.lifecycle.foreground_inspector`).
    """

    window_id: str
    name:      str
    trigger:   str = Trigger.CLICK
    pid:       int = 0


# A foreground target is a configured app, the synthetic add-app tile, or an
# external window.
Target = AppTarget | AddTileTarget | WindowTarget


def target_at_index(
    index:       int,
    apps:        Sequence[App],
    windows:     Sequence[Window],
    trigger_for: Callable[[int], str],
) -> Target | None:
    """The foreground Target at tile position *index*, or None if out of range.

    Tile layout is the configured apps first, then the synthetic ``[＋]`` add-app
    tile that ends the pinned section, then the open external windows: an index
    inside the app range is that ``AppTarget``; the position right after the apps
    is the :class:`AddTileTarget`; beyond it, the external window at that offset
    becomes a ``WindowTarget`` carrying the recall trigger it inherits
    (``trigger_for`` resolves a window's pid to its trigger — the parent-chain
    walk and /proc read behind it stay in infrastructure)."""
    if index < len(apps):
        return AppTarget(index=index, name=apps[index].name, is_game=apps[index].is_game)
    if index == len(apps):
        return AddTileTarget()
    win_idx = index - len(apps) - 1
    window = windows[win_idx] if win_idx < len(windows) else None
    if window is None:
        return None
    return WindowTarget(
        window_id=window.id, name=window.title,
        trigger=trigger_for(window.pid), pid=window.pid,
    )
