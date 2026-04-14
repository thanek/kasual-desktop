"""
Testy AppTile — maszyna stanów kropki (running / closing).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from desktop.app_tile import AppTile


@pytest.fixture
def tile(qapp):
    return AppTile(name="Test", icon_name="fa5s.desktop", color="#2e3440")


class TestDotRunning:
    def test_set_running_true_shows_dot(self, tile):
        tile.set_running(True)
        assert not tile._dot.isHidden()

    def test_set_running_false_hides_dot(self, tile):
        tile.set_running(True)
        tile.set_running(False)
        assert tile._dot.isHidden()

    def test_dot_hidden_by_default(self, tile):
        assert tile._dot.isHidden()

    def test_set_running_false_resets_closing_flag(self, tile):
        tile.set_closing()
        tile.set_running(False)
        assert tile._closing is False


class TestDotClosing:
    def test_set_closing_shows_dot(self, tile):
        tile.set_closing()
        assert not tile._dot.isHidden()

    def test_set_closing_sets_flag(self, tile):
        tile.set_closing()
        assert tile._closing is True

    def test_set_running_true_after_closing_keeps_dot_visible(self, tile):
        tile.set_closing()
        tile.set_running(True)   # _refresh_tile_status wywołuje to co 500 ms
        assert not tile._dot.isHidden()

    def test_set_running_true_after_closing_does_not_reset_flag(self, tile):
        tile.set_closing()
        tile.set_running(True)
        assert tile._closing is True

    def test_set_running_false_after_closing_hides_dot(self, tile):
        tile.set_closing()
        tile.set_running(False)  # proces zakończył działanie
        assert tile._dot.isHidden()

    def test_closing_dot_color_differs_from_running(self, tile):
        tile.set_running(True)
        green_style = tile._dot.styleSheet()
        tile.set_closing()
        orange_style = tile._dot.styleSheet()
        assert green_style != orange_style
