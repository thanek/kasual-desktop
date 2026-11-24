"""Editing a tile's per-tile settings — colour and recall-menu trigger. Each change
updates the shared live model *and* persists it, so the two never drift."""

from __future__ import annotations

from domain.catalog.live_catalog import LiveCatalog
from domain.menu.ports import TileSettingsStore


class TileSettingsEditor:
    def __init__(self, catalog: LiveCatalog, store: TileSettingsStore) -> None:
        self._catalog = catalog
        self._store   = store

    def set_color(self, index: int, color: str) -> None:
        self._catalog.recolour(index, color)
        self._store.set_color(index, color)

    def set_recall_trigger(self, index: int, trigger: str) -> None:
        self._catalog.set_recall_trigger(index, trigger)
        self._store.set_recall_trigger(index, trigger)
