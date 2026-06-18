"""Ports the menu/tile use-cases drive on the outside world."""

from typing import Protocol

from domain.catalog.app import App
from domain.catalog.window import Window


class TileOrderStore(Protocol):
    """Persists the app-tile order (the write side of the catalog's placement rule).

    The move-mode coordinator calls :meth:`swap` after each on-screen swap so the new
    order survives a restart. The indices are positions in the rendered tile order —
    i.e. the ``(X-Kasual-Order, source)``-sorted catalog — and the adapter rewrites the
    ``.desktop`` ``X-Kasual-Order`` keys to match.
    """

    def swap(self, i: int, j: int) -> None: ...


class TileColorStore(Protocol):
    """Persists a tile's colour (the write side of ``X-Kasual-Color``).

    The Tile Management Popover's colour picker calls :meth:`set_color` after
    recolouring a tile on screen, so the new colour survives a restart. *index* is
    the tile's position in the rendered order (the ``(X-Kasual-Order, source)``-sorted
    catalog) and the adapter rewrites that ``.desktop`` file's ``X-Kasual-Color``.
    """

    def set_color(self, index: int, color: str) -> None: ...


class AppPinning(Protocol):
    """Persists an open window as a permanent app tile (the *Pin to menu* action).

    Given the open *window*, the adapter resolves its source freedesktop
    ``.desktop`` entry (by app-id / ``StartupWMClass``), writes a Kasual app
    ``.desktop`` into the catalog directory, and returns the resulting
    :class:`App` so the tile bar can show it immediately. Returns ``None`` when the
    window cannot be resolved to a launchable command or the write fails — the
    caller surfaces that as a failure cue rather than a phantom tile.
    """

    def pin(self, window: Window) -> App | None: ...

    def unpin(self, index: int) -> None:
        """Delete the catalog ``.desktop`` of the app tile at *index* (the reverse
        of :meth:`pin`). *index* is the tile's position in the rendered order — the
        same ``(X-Kasual-Order, source)``-sorted catalog the order/colour stores
        key on. Removing it from the running tile bar is the caller's job; this only
        drops the persisted file so the tile is gone after a restart."""
        ...
