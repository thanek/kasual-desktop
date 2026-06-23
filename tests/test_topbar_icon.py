"""Tests for the top-bar dynamic action icon (used for the live network glyph)."""

from domain.system.actions import NETWORK


def _topbar(qapp):
    from infrastructure.common.qt.desktop.topbar import TopBar
    return TopBar()


class TestSetActionIcon:
    def test_swaps_the_button_icon(self, qapp):
        tb = _topbar(qapp)
        idx = tb._action_keys.index(NETWORK)
        before = tb._buttons[idx].icon().cacheKey()
        tb.set_action_icon(NETWORK, "mdi.wifi-off")
        assert tb._buttons[idx].icon().cacheKey() != before

    def test_unknown_action_is_ignored(self, qapp):
        tb = _topbar(qapp)
        tb.set_action_icon("does-not-exist", "fa5s.wifi")  # must not raise
