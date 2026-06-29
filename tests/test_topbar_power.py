"""Tests for the top bar's single Power button (§7.10).

The Power button carries the abstract POWER action and emits it on click (the
controller routes that to the persisted default); set_power_default mirrors the
default's glyph/tint so the bar matches the Home Overlay.
"""

from domain.menu.entry import POWER
from domain.system.action_view import topbar_items
from domain.system.actions import ACTIONS, RESTART, SLEEP


def _topbar(qapp):
    from infrastructure.common.qt.desktop.topbar import TopBar
    return TopBar(items=topbar_items(SLEEP))


class TestPowerButton:
    def test_click_emits_abstract_power(self, qapp):
        tb = _topbar(qapp)
        emitted = []
        tb.action_triggered.connect(emitted.append)
        idx = tb._action_keys.index(POWER)
        tb._buttons[idx].click()
        assert emitted == [POWER]

    def test_set_power_default_swaps_glyph_and_tint(self, qapp):
        tb = _topbar(qapp)
        idx = tb._action_keys.index(POWER)
        before = tb._buttons[idx].icon().cacheKey()
        tb.set_power_default(ACTIONS[RESTART].icon, ACTIONS[RESTART].color)
        assert tb._buttons[idx].icon().cacheKey() != before
        assert tb._colors[idx] == ACTIONS[RESTART].color

    def test_set_power_default_is_noop_without_power_button(self, qapp):
        from infrastructure.common.qt.desktop.topbar import TopBar
        tb = TopBar(items=[])                       # no Power button
        tb.set_power_default("fa5s.redo-alt", "#000000")   # must not raise
