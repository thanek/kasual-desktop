"""
Testy AppTile — maszyna stanów paska statusu (running / closing).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF
from PyQt6.QtGui import QEnterEvent

from desktop.app_tile import AppTile


@pytest.fixture
def tile(qapp):
    return AppTile(name="Test", icon_name="fa5s.desktop", color="#2e3440")


def _enter_at(pt: QPoint) -> QEnterEvent:
    p = QPointF(pt)
    return QEnterEvent(QPointF(0, 0), p, p)


class TestDotRunning:
    def test_set_running_true_shows_dot(self, tile):
        tile.set_running(True)
        assert not tile._status_bar.isHidden()

    def test_set_running_false_hides_dot(self, tile):
        tile.set_running(True)
        tile.set_running(False)
        assert tile._status_bar.isHidden()

    def test_dot_hidden_by_default(self, tile):
        assert tile._status_bar.isHidden()

    def test_set_running_false_resets_closing_flag(self, tile):
        tile.set_closing()
        tile.set_running(False)
        assert tile._closing is False


class TestDotClosing:
    def test_set_closing_shows_dot(self, tile):
        tile.set_closing()
        assert not tile._status_bar.isHidden()

    def test_set_closing_sets_flag(self, tile):
        tile.set_closing()
        assert tile._closing is True

    def test_set_running_true_after_closing_keeps_dot_visible(self, tile):
        tile.set_closing()
        tile.set_running(True)   # TileBar.refresh_status wywołuje to co 500 ms
        assert not tile._status_bar.isHidden()

    def test_set_running_true_after_closing_does_not_reset_flag(self, tile):
        tile.set_closing()
        tile.set_running(True)
        assert tile._closing is True

    def test_set_running_false_after_closing_hides_dot(self, tile):
        tile.set_closing()
        tile.set_running(False)  # proces zakończył działanie
        assert tile._status_bar.isHidden()

    def test_closing_dot_color_differs_from_running(self, tile):
        tile.set_running(True)
        green_style = tile._status_bar.styleSheet()
        tile.set_closing()
        orange_style = tile._status_bar.styleSheet()
        assert green_style != orange_style


class TestHoverSuppression:
    """A synthetic enterEvent (window above hidden, cursor stationary) must not
    be reported as a hover — otherwise the tile under the idle pointer steals
    selection when the Home Overlay is dismissed."""

    def test_enter_emits_hover_without_prior_leave(self, tile):
        seen = []
        tile.hovered.connect(lambda: seen.append(True))
        tile.enterEvent(_enter_at(QPoint(50, 50)))
        assert seen == [True]

    def test_enter_emits_hover_when_cursor_moved_since_leave(self, tile):
        seen = []
        tile.hovered.connect(lambda: seen.append(True))
        tile._pos_at_leave = QPoint(10, 10)
        tile.enterEvent(_enter_at(QPoint(50, 50)))   # cursor actually moved
        assert seen == [True]

    def test_enter_suppressed_when_cursor_unchanged_since_leave(self, tile):
        seen = []
        tile.hovered.connect(lambda: seen.append(True))
        tile._pos_at_leave = QPoint(50, 50)
        tile.enterEvent(_enter_at(QPoint(50, 50)))   # synthetic: same position
        assert seen == []

    def test_suppression_is_one_shot(self, tile):
        seen = []
        tile.hovered.connect(lambda: seen.append(True))
        tile._pos_at_leave = QPoint(50, 50)
        tile.enterEvent(_enter_at(QPoint(50, 50)))   # suppressed, clears state
        tile.enterEvent(_enter_at(QPoint(50, 50)))   # no stale leave → real hover
        assert seen == [True]

    def test_leave_records_cursor_position(self, tile):
        tile.leaveEvent(QEvent(QEvent.Type.Leave))
        assert isinstance(tile._pos_at_leave, QPoint)
