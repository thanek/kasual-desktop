"""Tile Popover menu composition — which entries appear for a focused tile.

Pure use-case (no Qt): decides the *structure* of the context Popover shown over
a tile, given what that tile is and whether it is running. Rendering (label,
icon, the callback wired to each entry) stays in the Application/Desktop wiring;
this owns only the composition rule:

  - a configured App that is not running → just "launch" it;
  - anything already on screen (a running App, or an open Window) → "restore" or
    "close" it.

Mirrors `domain.home_menu` — the Home Overlay's twin.
"""

from domain.catalog.target import AppTarget, Target
from domain.menu.entry import CLOSE, LAUNCH, RESTORE, MenuEntry


def compose_tile_menu(target: Target, is_running: bool) -> list[MenuEntry]:
    """Compose the tile Popover for *target*.

    `is_running` is only consulted for an :class:`AppTarget` (a configured app
    tile); an open :class:`WindowTarget` is by definition already running.
    """
    if isinstance(target, AppTarget) and not is_running:
        return [MenuEntry(LAUNCH)]
    return [MenuEntry(RESTORE), MenuEntry(CLOSE)]
