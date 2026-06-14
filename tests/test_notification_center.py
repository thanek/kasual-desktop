"""Tests for the NotificationCenter recent-notifications buffer."""

from datetime import datetime

from domain.notifications.center import NotificationCenter
from domain.notifications.notification import Notification
from domain.shared.event_emitter import EventEmitter


def _n(name: str) -> Notification:
    return Notification(app_name=name, summary=f"{name} summary",
                        timestamp=datetime(2026, 6, 14, 12, 0, 0))


class TestNotificationCenter:
    def test_empty_initially(self):
        c = NotificationCenter()
        assert c.count == 0
        assert c.recent() == []

    def test_records_newest_first(self):
        c = NotificationCenter()
        c.record(_n("A"))
        c.record(_n("B"))
        assert [n.app_name for n in c.recent()] == ["B", "A"]

    def test_count_tracks_size(self):
        c = NotificationCenter()
        c.record(_n("A"))
        c.record(_n("B"))
        assert c.count == 2

    def test_bounded_by_limit_dropping_oldest(self):
        c = NotificationCenter(limit=3)
        for name in ("A", "B", "C", "D", "E"):
            c.record(_n(name))
        assert [n.app_name for n in c.recent()] == ["E", "D", "C"]
        assert c.count == 3

    def test_recent_caps_further(self):
        c = NotificationCenter()
        for name in ("A", "B", "C"):
            c.record(_n(name))
        assert [n.app_name for n in c.recent(2)] == ["C", "B"]


class TestUnread:
    def test_empty_has_no_unread(self):
        assert NotificationCenter().unread_count == 0

    def test_recording_increments_unread(self):
        c = NotificationCenter()
        c.record(_n("A"))
        c.record(_n("B"))
        assert c.unread_count == 2

    def test_mark_all_read_clears_unread(self):
        c = NotificationCenter()
        c.record(_n("A"))
        c.mark_all_read()
        assert c.unread_count == 0
        assert c.count == 1   # the notification itself is still retained

    def test_unread_counts_only_since_last_read(self):
        c = NotificationCenter()
        c.record(_n("A"))
        c.mark_all_read()
        c.record(_n("B"))
        assert c.unread_count == 1

    def test_unread_never_exceeds_retained(self):
        c = NotificationCenter(limit=3)
        for name in ("A", "B", "C", "D", "E"):
            c.record(_n(name))
        assert c.unread_count == 3   # capped at the buffer size, not 5


class TestSourceWiring:
    def test_records_from_a_source_port(self):
        """The composition root wires source.on_notification(center.record);
        a fake source emitting should reach the center."""
        emitter: EventEmitter[Notification] = EventEmitter()
        center = NotificationCenter()
        emitter.subscribe(center.record)   # == monitor.on_notification(center.record)

        emitter.emit(_n("Spotify"))
        assert [n.app_name for n in center.recent()] == ["Spotify"]
