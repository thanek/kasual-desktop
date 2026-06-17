"""Tests for AppCatalog — the domain placement rule for the app catalog.

The freedesktop→App mapping is tested in test_domain_app.py; the file I/O in
test_app_config.py. Here we pin the ordering rule (X-Kasual-Order ascending,
ties broken by source) and the Sequence behaviour consumers rely on.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from collections.abc import Sequence

from domain.catalog.app import App
from domain.catalog.catalog import AppCatalog


def _app(name: str) -> App:
    return App(name=name, command=name.lower())


class TestFromEntries:
    def test_orders_by_ascending_order_key(self):
        cat = AppCatalog.from_entries([
            (20, "b.desktop", _app("B")),
            (10, "a.desktop", _app("A")),
        ])
        assert [a.name for a in cat] == ["A", "B"]

    def test_ties_broken_by_source(self):
        cat = AppCatalog.from_entries([
            (10, "z.desktop", _app("Z")),
            (10, "a.desktop", _app("A")),
            (10, "m.desktop", _app("M")),
        ])
        assert [a.name for a in cat] == ["A", "M", "Z"]

    def test_explicit_order_before_default(self):
        # ORDER_DEFAULT (large) entries fall after explicitly-ordered ones.
        cat = AppCatalog.from_entries([
            (10_000, "z.desktop", _app("Z")),
            (10,     "a.desktop", _app("A")),
            (10_000, "m.desktop", _app("M")),
        ])
        assert [a.name for a in cat] == ["A", "M", "Z"]

    def test_empty(self):
        assert list(AppCatalog.from_entries([])) == []


class TestSwapped:
    def test_exchanges_two_positions(self):
        cat = AppCatalog((_app("A"), _app("B"), _app("C")))
        out = cat.swapped(0, 2)
        assert [a.name for a in out] == ["C", "B", "A"]

    def test_adjacent_swap(self):
        cat = AppCatalog((_app("A"), _app("B"), _app("C")))
        out = cat.swapped(0, 1)
        assert [a.name for a in out] == ["B", "A", "C"]

    def test_leaves_original_untouched(self):
        cat = AppCatalog((_app("A"), _app("B")))
        cat.swapped(0, 1)
        assert [a.name for a in cat] == ["A", "B"]


class TestSequenceBehaviour:
    def test_is_a_sequence(self):
        assert isinstance(AppCatalog(), Sequence)

    def test_index_len_iterate(self):
        cat = AppCatalog((_app("A"), _app("B")))
        assert len(cat) == 2
        assert cat[0].name == "A"
        assert cat[1].name == "B"
        assert [a.name for a in cat] == ["A", "B"]

    def test_default_is_empty(self):
        assert len(AppCatalog()) == 0
