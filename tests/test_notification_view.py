"""Tests for the relative-age notification label (domain presentation helper)."""

from datetime import datetime, timedelta

from domain.notifications.view import relative_age

_NOW = datetime(2026, 6, 14, 12, 0, 0)


class TestRelativeAge:
    def test_just_now_under_a_minute(self):
        assert relative_age(_NOW - timedelta(seconds=10), _NOW) == "just now"

    def test_clock_skew_into_future_is_just_now(self):
        assert relative_age(_NOW + timedelta(seconds=5), _NOW) == "just now"

    def test_minutes(self):
        assert relative_age(_NOW - timedelta(minutes=5), _NOW) == "5 min ago"

    def test_minutes_floor(self):
        assert relative_age(_NOW - timedelta(minutes=2, seconds=59), _NOW) == "2 min ago"

    def test_hours(self):
        assert relative_age(_NOW - timedelta(hours=3), _NOW) == "3 h ago"

    def test_older_than_a_day_is_a_date(self):
        ts = _NOW - timedelta(days=2)
        assert relative_age(ts, _NOW) == ts.strftime("%Y-%m-%d")
