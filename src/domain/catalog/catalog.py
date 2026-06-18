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
from dataclasses import dataclass, replace

from domain.catalog.app import App
from domain.input.vocabulary import Trigger


def _inherit_steam_recall_trigger(apps: list[App]) -> list[App]:
    """Give each Steam game tile the Steam launcher tile's recall trigger, unless
    it set one of its own.

    Steam game tiles (``steam steam://rungameid/<id>``) are launched through the
    Steam client tile (``steam.desktop``), so BTN_MODE should behave the same
    over a game as over Steam itself — e.g. its ``X-Kasual-RecallMenuTrigger=
    BTN_MODE_HOLD_1S`` hold-to-recall. A game keeps its own trigger when it
    declares one; "no setting" is the default :data:`Trigger.CLICK` (the same
    sentinel ``App.to_desktop_entry`` omits when serialising), so a game left at
    the default inherits, and one explicitly configured does not.

    Pure: the inheritance lives only in the in-memory catalog and is never
    written back to the game's ``.desktop`` file.
    """
    launcher = next(
        (a for a in apps if a.command_basename == "steam" and a.steam_app_id is None),
        None,
    )
    if launcher is None or launcher.recall_menu_trigger == Trigger.CLICK:
        return apps
    return [
        replace(app, recall_menu_trigger=launcher.recall_menu_trigger)
        if app.steam_app_id is not None and app.recall_menu_trigger == Trigger.CLICK
        else app
        for app in apps
    ]


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
        apps = _inherit_steam_recall_trigger([app for _, _, app in ordered])
        return cls(tuple(apps))

    def swapped(self, i: int, j: int) -> "AppCatalog":
        """Return a new catalog with the apps at positions *i* and *j* exchanged.

        Pure (the catalog is immutable): the tile bar's move mode uses this to
        reorder app tiles, with the parallel ``.desktop`` ``X-Kasual-Order`` rewrite
        handled by the persistence adapter.
        """
        apps = list(self.apps)
        apps[i], apps[j] = apps[j], apps[i]
        return AppCatalog(tuple(apps))

    def appended(self, app: App) -> "AppCatalog":
        """Return a new catalog with *app* added at the end.

        Pure (the catalog is immutable): the *Pin to menu* action uses this to add
        a newly-pinned open window as the last app tile, with the parallel
        ``.desktop`` write handled by the persistence adapter.
        """
        return AppCatalog((*self.apps, app))

    def removed(self, index: int) -> "AppCatalog":
        """Return a new catalog without the app at *index*.

        Pure (the catalog is immutable): the *Unpin* action uses this to drop a
        tile, with the parallel ``.desktop`` deletion handled by the persistence
        adapter.
        """
        apps = list(self.apps)
        del apps[index]
        return AppCatalog(tuple(apps))

    def with_color(self, index: int, color: str) -> "AppCatalog":
        """Return a new catalog with the app at *index* recoloured to *color*.

        Pure (the catalog and its apps are immutable): the tile bar's colour
        change uses this, with the parallel ``.desktop`` ``X-Kasual-Color`` rewrite
        handled by the persistence adapter.
        """
        apps = list(self.apps)
        apps[index] = replace(apps[index], color=color)
        return AppCatalog(tuple(apps))

    def __getitem__(self, index):
        return self.apps[index]

    def __len__(self) -> int:
        return len(self.apps)
