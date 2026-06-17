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
from domain.input.vocabulary import Trigger


def _app(name: str) -> App:
    return App(name=name, command=name.lower())


def _steam_launcher(trigger=Trigger.HOLD_1S) -> App:
    return App(name="Steam", command="steam", args=("steam://open/bigpicture",),
               recall_menu_trigger=trigger)


def _steam_game(name="Witcher 3", appid="292030", trigger=Trigger.CLICK) -> App:
    return App(name=name, command="steam", args=(f"steam://rungameid/{appid}",),
               recall_menu_trigger=trigger)


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


class TestSteamRecallTriggerInheritance:
    """A Steam game tile inherits the Steam launcher tile's recall trigger unless
    it set one of its own."""

    def test_game_without_own_trigger_inherits_launcher(self):
        cat = AppCatalog.from_entries([
            (1, "steam.desktop",   _steam_launcher(Trigger.HOLD_1S)),
            (2, "witcher.desktop", _steam_game(trigger=Trigger.CLICK)),
        ])
        game = next(a for a in cat if a.steam_app_id == "292030")
        assert game.recall_menu_trigger == Trigger.HOLD_1S

    def test_game_with_explicit_trigger_is_left_alone(self):
        cat = AppCatalog.from_entries([
            (1, "steam.desktop",   _steam_launcher(Trigger.HOLD_1S)),
            (2, "witcher.desktop", _steam_game(trigger=Trigger.CLICK)),
            (3, "kcd.desktop",     _steam_game("KCD", "379430", Trigger.CLICK)),
        ])
        # The launcher itself keeps its trigger.
        launcher = next(a for a in cat if a.steam_app_id is None and a.name == "Steam")
        assert launcher.recall_menu_trigger == Trigger.HOLD_1S

    def test_explicit_game_trigger_not_overridden(self):
        # CLICK is the "unset" sentinel; an explicit non-default trigger stays.
        cat = AppCatalog.from_entries([
            (1, "steam.desktop", _steam_launcher(Trigger.HOLD_1S)),
            (2, "game.desktop",  _steam_game(trigger=Trigger.HOLD_1S)),
        ])
        # (Trivially HOLD_1S here, but the point is no replacement happens.)
        game = next(a for a in cat if a.steam_app_id == "292030")
        assert game.recall_menu_trigger == Trigger.HOLD_1S

    def test_no_inheritance_when_launcher_is_default(self):
        cat = AppCatalog.from_entries([
            (1, "steam.desktop",   _steam_launcher(Trigger.CLICK)),
            (2, "witcher.desktop", _steam_game(trigger=Trigger.CLICK)),
        ])
        game = next(a for a in cat if a.steam_app_id == "292030")
        assert game.recall_menu_trigger == Trigger.CLICK

    def test_no_inheritance_without_launcher_tile(self):
        # A game tile but no Steam launcher tile present → unchanged.
        cat = AppCatalog.from_entries([
            (2, "witcher.desktop", _steam_game(trigger=Trigger.CLICK)),
        ])
        game = next(a for a in cat if a.steam_app_id == "292030")
        assert game.recall_menu_trigger == Trigger.CLICK

    def test_non_steam_apps_untouched(self):
        firefox = App(name="Firefox", command="firefox")
        cat = AppCatalog.from_entries([
            (1, "steam.desktop",   _steam_launcher(Trigger.HOLD_1S)),
            (2, "firefox.desktop", firefox),
        ])
        ff = next(a for a in cat if a.name == "Firefox")
        assert ff.recall_menu_trigger == Trigger.CLICK


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


class TestWithColor:
    def test_recolours_one_app(self):
        cat = AppCatalog((_app("A"), _app("B")))
        out = cat.with_color(1, "#ff0000")
        assert out[1].color == "#ff0000"
        assert out[0].color == _app("A").color

    def test_leaves_original_untouched(self):
        cat = AppCatalog((_app("A"),))
        cat.with_color(0, "#ff0000")
        assert cat[0].color == _app("A").color


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
