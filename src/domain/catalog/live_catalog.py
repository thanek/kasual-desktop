"""The single, shared, mutable view of the current app order.

The catalog is reordered (move mode) and recoloured at runtime, yet several
index-keyed consumers — the tile bar, the app-lifecycle coordinator and the
deferred hide — must all agree on which app sits at which position. Handing each
its own immutable :class:`AppCatalog` let them drift: a reorder rebuilt only the
tile bar's copy, so the lifecycle still launched (and closed) whatever app *used*
to occupy that index. They share one :class:`LiveCatalog` instead, so a single
``swap``/``recolour`` is seen by every consumer at once.

It is a read-only ``Sequence[App]`` to its consumers (index/len/iterate), exactly
like :class:`AppCatalog`; only the two mutators rebind the wrapped catalog.
"""

from collections.abc import Iterator, Sequence

from domain.catalog.app import App
from domain.catalog.catalog import AppCatalog


class LiveCatalog(Sequence[App]):
    """Mutable, shared-by-reference holder of the current :class:`AppCatalog`."""

    def __init__(self, catalog: AppCatalog) -> None:
        self._catalog = catalog

    @property
    def catalog(self) -> AppCatalog:
        return self._catalog

    def swap(self, i: int, j: int) -> None:
        """Exchange the apps at positions *i* and *j*, for every consumer at once."""
        self._catalog = self._catalog.swapped(i, j)

    def recolour(self, index: int, color: str) -> None:
        """Recolour the app at *index*, for every consumer at once."""
        self._catalog = self._catalog.with_color(index, color)

    def append(self, app: App) -> None:
        """Add *app* as the last tile, for every consumer at once (the pin action)."""
        self._catalog = self._catalog.appended(app)

    def remove(self, index: int) -> None:
        """Drop the tile at *index*, for every consumer at once (the unpin action)."""
        self._catalog = self._catalog.removed(index)

    def __getitem__(self, index):
        return self._catalog[index]

    def __len__(self) -> int:
        return len(self._catalog)

    def __iter__(self) -> Iterator[App]:
        return iter(self._catalog)
