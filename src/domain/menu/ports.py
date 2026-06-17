"""Ports the menu/tile use-cases drive on the outside world."""

from typing import Protocol


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
