"""Tests for compose_home_menu — the BTN_MODE menu composition rule.

Pure decision over the foreground target; no Qt, no rendering. Labels come back
localized; with no translator installed `support.i18n` is the identity, so they
equal the source strings.
"""

from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.home import compose_home_menu
from domain.catalog.target import AppTarget, WindowTarget


class TestIdle:
    def test_starts_with_return_to_desktop(self):
        menu = compose_home_menu(None)
        assert menu.items[0].action == RETURN_TO_DESKTOP

    def test_includes_system_actions(self):
        menu = compose_home_menu(None)
        # the system actions (volume/sleep/…) follow return-to-desktop
        assert {"volume", "sleep", "restart", "shutdown", "hide_desktop"} <= {
            i.action for i in menu.items
        }

    def test_cancel_does_not_restore(self):
        menu = compose_home_menu(None)
        assert menu.cancel_restores is None


class TestForegroundApp:
    def test_app_control_items_in_order(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert [i.action for i in menu.items] == [
            RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP,
        ]

    def test_carries_target_on_control_items(self):
        target = AppTarget(index=0, name="Steam")
        menu = compose_home_menu(target)
        assert menu.items[0].target == target   # return
        assert menu.items[1].target == target   # close
        assert menu.items[2].target is None      # return-to-desktop: no target

    def test_labels_carry_app_name(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert "Steam" in menu.items[0].label   # "Return to Steam"
        assert "Steam" in menu.items[1].label   # "Close Steam"

    def test_no_system_actions_over_app(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert all(i.action in (RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP)
                   for i in menu.items)

    def test_cancel_restores_running_app(self):
        target = AppTarget(index=0, name="Steam")
        menu = compose_home_menu(target)
        assert menu.cancel_restores == target

    def test_window_target_used_for_cancel_and_label(self):
        target = WindowTarget(window_id="w1", name="Game")
        menu = compose_home_menu(target)
        assert "Game" in menu.items[0].label
        assert menu.cancel_restores == target
