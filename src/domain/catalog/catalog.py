"""The launcher's app catalog — the ordered collection of configured apps.

Loading apps is two things: reading the ``.desktop`` files (I/O, the
``system.app_config`` adapter) and *placing* them into the launcher's order.
That ordering is a domain rule — apps appear by their ``X-Kasual-Order``
(ascending), and entries without one fall to the end — so it lives here, not in
the loader. The adapter feeds parsed ``(order, source, App)`` entries to
:meth:`AppCatalog.from_entries`; ``source`` (e.g. the ``.desktop`` filename) is
the stable tie-breaker for entries sharing an order.

``AppCatalog`` is a read-only ``Sequence[App]``: indexing, ``len`` and iteration
work as on a list, so it drops into every consumer that used ``list[App]``.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from domain.catalog.app import App


@dataclass(frozen=True)
class AppCatalog(Sequence[App]):
    """The ordered catalog of configured apps. Immutable; index/len/iterate."""

    apps: tuple[App, ...] = ()

    @classmethod
    def from_entries(cls, entries: Iterable[tuple[int, str, App]]) -> "AppCatalog":
        """Build the catalog from parsed ``(order, source, app)`` entries.

        Placement rule: ascending ``order`` (the ``X-Kasual-Order`` key), ties
        broken by ``source`` so the result is stable and predictable.
        """
        ordered = sorted(entries, key=lambda e: (e[0], e[1]))
        return cls(tuple(app for _, _, app in ordered))

    def swapped(self, i: int, j: int) -> "AppCatalog":
        """Return a new catalog with the apps at positions *i* and *j* exchanged.

        Pure (the catalog is immutable): the tile bar's move mode uses this to
        reorder app tiles, with the parallel ``.desktop`` ``X-Kasual-Order`` rewrite
        handled by the persistence adapter.
        """
        apps = list(self.apps)
        apps[i], apps[j] = apps[j], apps[i]
        return AppCatalog(tuple(apps))

    def __getitem__(self, index):
        return self.apps[index]

    def __len__(self) -> int:
        return len(self.apps)
