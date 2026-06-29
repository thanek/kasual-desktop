"""Tests for the top-bar action badge (used for the notification count)."""

from domain.system.actions import NOTIFICATIONS


def _topbar(qapp):
    from infrastructure.common.qt.desktop.topbar import TopBar
    return TopBar()


class TestSetBadge:
    def test_shows_count(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 3)
        badge = tb._badges[NOTIFICATIONS]
        assert badge.text() == "3"
        assert not badge.isHidden()

    def test_zero_hides_badge(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 5)
        tb.set_badge(NOTIFICATIONS, 0)
        assert tb._badges[NOTIFICATIONS].isHidden()

    def test_caps_counts_over_nine(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 10)
        assert tb._badges[NOTIFICATIONS].text() == "9+"

    def test_single_digit_shown_verbatim(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 9)
        assert tb._badges[NOTIFICATIONS].text() == "9"

    def test_badge_is_a_fixed_circle(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 15)
        badge = tb._badges[NOTIFICATIONS]
        assert (badge.width(), badge.height()) == (20, 20)

    def test_unknown_action_is_ignored(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge("does-not-exist", 4)
        assert "does-not-exist" not in tb._badges

    def test_badge_is_a_child_of_its_button(self, qapp):
        tb = _topbar(qapp)
        tb.set_badge(NOTIFICATIONS, 1)
        idx = tb._action_keys.index(NOTIFICATIONS)
        assert tb._badges[NOTIFICATIONS].parent() is tb._buttons[idx]
