"""Tests for compose_home_menu — the BTN_MODE menu composition rule.

Pure decision over the foreground target; no Qt, no rendering. Labels come back
localized; with no translator installed `support.i18n` is the identity, so they
equal the source strings.
"""

from domain.menu.entry import (
    CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP, TOGGLE_HUD,
)
from domain.menu.home import compose_home_menu
from domain.catalog.target import AppTarget, WindowTarget


class FakeHud:
    """HudControl stub — availability/state fixed per test."""

    def __init__(self, available=False, enabled=True):
        self._available = available
        self._enabled = enabled

    def is_available(self):
        return self._available

    def is_enabled(self):
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


class TestIdle:
    def test_starts_with_return_to_desktop(self):
        menu = compose_home_menu(None, FakeHud())
        assert menu.items[0].action == RETURN_TO_DESKTOP

    def test_includes_system_actions(self):
        menu = compose_home_menu(None, FakeHud())
        # the system actions (volume/sleep/…) follow return-to-desktop
        assert {"volume", "sleep", "restart", "shutdown", "hide_desktop"} <= {
            i.action for i in menu.items
        }

    def test_cancel_does_not_restore(self):
        menu = compose_home_menu(None, FakeHud())
        assert menu.cancel_restores is None

    def test_no_hud_toggle_on_desktop(self):
        # The HUD toggle is a game-mode affordance; it never appears on the
        # bare Desktop, even when a HUD is available.
        menu = compose_home_menu(None, FakeHud(available=True))
        assert all(i.action != TOGGLE_HUD for i in menu.items)


class TestForegroundApp:
    def test_app_control_items_in_order(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"), FakeHud())
        assert [i.action for i in menu.items] == [
            RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP,
        ]

    def test_carries_target_on_control_items(self):
        target = AppTarget(index=0, name="Steam")
        menu = compose_home_menu(target, FakeHud())
        assert menu.items[0].target == target   # return
        assert menu.items[1].target == target   # close
        assert menu.items[2].target is None      # return-to-desktop: no target

    def test_labels_carry_app_name(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"), FakeHud())
        assert "Steam" in menu.items[0].label   # "Return to Steam"
        assert "Steam" in menu.items[1].label   # "Close Steam"

    def test_no_system_actions_over_app(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"), FakeHud())
        assert all(i.action in (RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP)
                   for i in menu.items)

    def test_cancel_restores_running_app(self):
        target = AppTarget(index=0, name="Steam")
        menu = compose_home_menu(target, FakeHud())
        assert menu.cancel_restores == target

    def test_window_target_used_for_cancel_and_label(self):
        target = WindowTarget(window_id="w1", name="Game")
        menu = compose_home_menu(target, FakeHud())
        assert "Game" in menu.items[0].label
        assert menu.cancel_restores == target


class TestHudToggleOverApp:
    def test_offered_before_return_to_desktop_when_available(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"), FakeHud(available=True))
        assert [i.action for i in menu.items] == [
            RETURN_TO_APP, CLOSE_APP, TOGGLE_HUD, RETURN_TO_DESKTOP,
        ]

    def test_hidden_when_unavailable(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"), FakeHud(available=False))
        assert all(i.action != TOGGLE_HUD for i in menu.items)

    def test_reads_disable_while_hud_on(self):
        menu = compose_home_menu(
            AppTarget(index=0, name="Steam"), FakeHud(available=True, enabled=True),
        )
        hud_item = next(i for i in menu.items if i.action == TOGGLE_HUD)
        assert hud_item.label == "Disable HUD"

    def test_reads_enable_while_hud_off(self):
        menu = compose_home_menu(
            AppTarget(index=0, name="Steam"), FakeHud(available=True, enabled=False),
        )
        hud_item = next(i for i in menu.items if i.action == TOGGLE_HUD)
        assert hud_item.label == "Enable HUD"
