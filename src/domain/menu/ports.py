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
