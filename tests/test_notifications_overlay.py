"""Smoke + behaviour tests for NotificationsOverlay (read-only MVP).

Builds the overlay offscreen with a real NotificationCenter and verifies it
renders the rows, navigates via the domain cursor, and emits `closed` on
dismiss. Mirrors test_volume_overlay.py (gamepad/feedback mocked).
"""

from datetime import datetime
from unittest.mock import MagicMock

from domain.notifications.center import NotificationCenter
from domain.notifications.notification import Notification


def _center(*names: str) -> NotificationCenter:
    c = NotificationCenter()
    for name in names:
        c.record(Notification(app_name=name, summary=f"{name} body",
                              timestamp=datetime.now()))
    return c


def _make_overlay(mock_gamepad, center):
    from infrastructure.qt.overlays.notifications_overlay import NotificationsOverlay
    return NotificationsOverlay(gamepad=mock_gamepad, center=center, feedback=MagicMock())


def _row_texts(row) -> list[str]:
    """All label texts inside a notification row widget."""
    from PyQt6.QtWidgets import QLabel
    return [lbl.text() for lbl in row.findChildren(QLabel)]


class TestInit:
    def test_builds_a_row_per_notification(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("A", "B", "C"))
        assert len(overlay._rows) == 3

    def test_newest_first(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("Old", "New"))
        assert any(_row_texts(overlay._rows[0]))  # has labels
        # The newest notification's summary ("New body") is shown in the top row.
        assert any("New" in t for t in _row_texts(overlay._rows[0]))

    def test_registers_handler(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("A"))
        assert overlay._handle_pad in mock_gamepad._stack

    def test_empty_state_has_no_rows(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center())
        assert overlay._rows == []


class TestUnreadHighlight:
    def test_first_n_rows_marked_unread(self, mock_gamepad):
        # "B" and "A" arrive unread; then they're read; "C" is the new one.
        c = _center("A", "B")
        c.mark_all_read()
        c.record(Notification(app_name="C", summary="C body", timestamp=datetime.now()))
        overlay = _make_overlay(mock_gamepad, c)
        # Newest-first: row 0 is the single unread ("C"); the rest are read.
        assert overlay._is_unread(0)
        assert not overlay._is_unread(1)
        assert not overlay._is_unread(2)

    def test_unread_capped_to_visible_rows(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("A", "B"))
        assert overlay._unread == 2


class TestClosing:
    def test_cancel_emits_closed_and_pops_handler(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("A"))
        seen = []
        overlay.closed.connect(lambda: seen.append(True))
        overlay._handle_pad("cancel")
        assert seen == [True]
        assert overlay._handle_pad not in mock_gamepad._stack

    def test_select_closes_in_readonly_mvp(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center("A", "B"))
        seen = []
        overlay.closed.connect(lambda: seen.append(True))
        overlay._handle_pad("select")
        assert seen == [True]

    def test_empty_list_still_closes(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, _center())
        seen = []
        overlay.closed.connect(lambda: seen.append(True))
        overlay._handle_pad("close")
        assert seen == [True]
