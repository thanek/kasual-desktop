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

from domain.catalog.target import AddTileTarget, AppTarget, Target
from domain.menu.entry import (
    CHANGE_COLOR, CLOSE, LAUNCH, MOVE, PIN, RESTORE, SEPARATOR, UNPIN,
)
from domain.menu.item import MenuItem
from domain.shared.i18n import translate

# A shared, immutable divider between the lifecycle and management groups (§7.3).
_SEPARATOR = MenuItem("", SEPARATOR)


def tile_menu_for(
    target: Target, is_running: Callable[[int], bool]
) -> list[MenuItem]:
    """Compose the unified tile Popover for *target*, resolving its running state.

    The running check is only meaningful for an :class:`AppTarget` (queried via
    *is_running* by index); an open :class:`WindowTarget` is by definition already
    running. The synthetic :class:`AddTileTarget` has no menu at all. Keeps that
    rule in the domain rather than in the Qt widget.
    """
    if isinstance(target, AddTileTarget):
        return []
    running = is_running(target.index) if isinstance(target, AppTarget) else True
    return compose_tile_menu(target, running)


def compose_tile_menu(target: Target, is_running: bool) -> list[MenuItem]:
    """The single, state-dependent tile menu (§7.3).

    The lifecycle action(s) on top, then — *unless the app is running* — a
    separator and the management group. A running catalog app is no moment to
    move / recolour / unpin it, so that group is dropped; an open window still
    offers the one durable action, *Pin to menu*.

      - catalog app · idle    → Launch · ─ · Move · Change color · Unpin
      - catalog app · running → Restore · Close          (management hidden)
      - ephemeral window      → Restore · Close · ─ · Pin to menu
    """
    lifecycle = lifecycle_menu(target, is_running)
    if isinstance(target, AppTarget) and is_running:
        return lifecycle
    return [*lifecycle, _SEPARATOR, *tile_management_menu(target)]


def lifecycle_menu(target: Target, is_running: bool) -> list[MenuItem]:
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
    """Compose the management group of the tile menu for *target*.

    The building block :func:`compose_tile_menu` appends below the separator:
    rather than launch/restore/close, it offers actions that manage the tile
    itself. A configured app tile can be moved, recoloured and unpinned (removed
    from the menu); an open-window tile is not part of the persistent catalog, so
    its only management action is *pinning* it — promoting it to a permanent app
    tile.
    """
    if isinstance(target, AppTarget):
        return [
            MenuItem(translate("Desktop", "Move"), MOVE, target=target),
            MenuItem(translate("Desktop", "Change color"), CHANGE_COLOR, target=target),
            MenuItem(translate("Desktop", "Unpin"), UNPIN, target=target),
        ]
    return [MenuItem(translate("Desktop", "Pin to menu"), PIN, target=target)]
