"""Tests for the top-bar button composition (topbar_items) — pure, no Qt.

The bar collapses the Sleep/Restart/Shut Down trio into a single Power button
(glyph mirrors the persisted default) and drops Volume/Brightness, which now live
in the Home Overlay's Quick adjust (§7.10).
"""

from domain.menu.entry import POWER
from domain.system.action_view import topbar_items
from domain.system.actions import (
    ACTIONS, BRIGHTNESS, HIDE_DESKTOP, NETWORK, NOTIFICATIONS, RESTART, SLEEP, VOLUME,
)


def _actions(items):
    return [i.action for i in items]


class TestComposition:
    def test_collapses_to_power_network_notif_minimize(self):
        assert _actions(topbar_items(SLEEP)) == [
            POWER, NETWORK, NOTIFICATIONS, HIDE_DESKTOP,
        ]

    def test_drops_volume_brightness_and_the_trio(self):
        actions = _actions(topbar_items(SLEEP))
        for gone in (VOLUME, BRIGHTNESS, SLEEP, RESTART):
            assert gone not in actions

    def test_power_glyph_mirrors_default(self):
        sleep_item = topbar_items(SLEEP)[0]
        assert sleep_item.action == POWER
        assert sleep_item.icon == ACTIONS[SLEEP].icon
        restart_item = topbar_items(RESTART)[0]
        assert restart_item.icon == ACTIONS[RESTART].icon
        assert restart_item.color == ACTIONS[RESTART].color
