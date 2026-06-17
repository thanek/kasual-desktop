"""Tile Popover menu composition — which items appear for a focused tile.

Pure use-case (no Qt): composes the render-ready context Popover shown over a
tile, given what that tile is and whether it is running:

  - a configured App that is not running → just "launch" it;
  - anything already on screen (a running App, or an open Window) → "restore" or
    "close" it.

Mirrors `domain.menu.home` — the Home Overlay's twin. Labels keep the "Desktop"
translation context so the existing locale entries keep resolving.
"""

from collections.abc import Callable

from domain.catalog.target import AppTarget, Target
from domain.menu.entry import CHANGE_COLOR, CLOSE, LAUNCH, MOVE, RESTORE
from domain.menu.item import MenuItem
from domain.shared.i18n import translate


def tile_menu_for(
    target: Target, is_running: Callable[[int], bool]
) -> list[MenuItem]:
    """Compose the tile Popover for *target*, resolving its running state.

    The running check is only meaningful for an :class:`AppTarget` (queried via
    *is_running* by index); an open :class:`WindowTarget` is by definition already
    running. Keeps that rule in the domain rather than in the Qt widget.
    """
    running = is_running(target.index) if isinstance(target, AppTarget) else True
    return compose_tile_menu(target, running)


def compose_tile_menu(target: Target, is_running: bool) -> list[MenuItem]:
    """Compose the tile Popover for *target*.

    `is_running` is only consulted for an :class:`AppTarget` (a configured app
    tile); an open :class:`WindowTarget` is by definition already running.
    """
    if isinstance(target, AppTarget) and not is_running:
        return [MenuItem(translate("Desktop", "Launch"), LAUNCH, target=target)]
    return [
        MenuItem(translate("Desktop", "Restore"), RESTORE, target=target),
        MenuItem(translate("Desktop", "Close"), CLOSE, target=target),
    ]


def tile_management_menu(target: Target) -> list[MenuItem]:
    """Compose the Tile Management Popover for *target* (the Start-button menu).

    A sibling of :func:`tile_menu_for`: rather than launch/restore/close, it offers
    actions that manage the tile itself — moving it, and recolouring it.
    """
    return [
        MenuItem(translate("Desktop", "Move"), MOVE, target=target),
        MenuItem(translate("Desktop", "Change color"), CHANGE_COLOR, target=target),
    ]
