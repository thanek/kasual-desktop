"""Tests for the HUD toggle's rough logic — hud_menu_item / toggle_hud.

Pure decisions over a HudControl stub plus the foreground-is-game flag; no
filesystem, no Qt. Labels come back localized; with no translator installed
`support.i18n` is the identity, so they equal the source strings.
"""

from domain.menu.entry import TOGGLE_HUD
from domain.system.hud import hud_menu_item, toggle_hud


class FakeHud:
    def __init__(self, available=True, enabled=True):
        self._available = available
        self.enabled = enabled

    def is_available(self): return self._available
    def is_enabled(self): return self.enabled
    def enable(self): self.enabled = True
    def disable(self): self.enabled = False


class TestMenuItem:
    def test_none_when_unavailable(self):
        assert hud_menu_item(FakeHud(available=False), foreground_is_game=True) is None

    def test_none_when_not_a_game(self):
        assert hud_menu_item(FakeHud(available=True), foreground_is_game=False) is None

    def test_offered_for_game(self):
        assert hud_menu_item(FakeHud(available=True), foreground_is_game=True) is not None

    def test_disable_label_while_on(self):
        item = hud_menu_item(FakeHud(available=True, enabled=True), foreground_is_game=True)
        assert item.action == TOGGLE_HUD
        assert item.label == "Disable HUD"

    def test_enable_label_while_off(self):
        item = hud_menu_item(FakeHud(available=True, enabled=False), foreground_is_game=True)
        assert item.action == TOGGLE_HUD
        assert item.label == "Enable HUD"


class TestToggle:
    def test_on_turns_off(self):
        hud = FakeHud(enabled=True)
        toggle_hud(hud)
        assert hud.enabled is False

    def test_off_turns_on(self):
        hud = FakeHud(enabled=False)
        toggle_hud(hud)
        assert hud.enabled is True
