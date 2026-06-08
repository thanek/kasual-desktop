"""Tests for compose_home_menu — the BTN_MODE menu composition rule.

Pure decision over the foreground target; no Qt, no rendering.
"""

from application.home_menu import (
    CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP, compose_home_menu,
)
from domain.target import AppTarget, WindowTarget


class TestIdle:
    def test_only_return_to_desktop(self):
        menu = compose_home_menu(None)
        assert [e.kind for e in menu.entries] == [RETURN_TO_DESKTOP]

    def test_includes_system_actions(self):
        menu = compose_home_menu(None)
        assert menu.include_system_actions is True

    def test_cancel_does_not_restore(self):
        menu = compose_home_menu(None)
        assert menu.cancel_restores_app is False


class TestForegroundApp:
    def test_app_control_entries_in_order(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert [e.kind for e in menu.entries] == [
            RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP,
        ]

    def test_carries_app_name_on_control_entries(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert menu.entries[0].name == "Steam"   # return
        assert menu.entries[1].name == "Steam"   # close
        assert menu.entries[2].name == ""        # return-to-desktop: no name

    def test_no_system_actions_over_app(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert menu.include_system_actions is False

    def test_cancel_restores_running_app(self):
        menu = compose_home_menu(AppTarget(index=0, name="Steam"))
        assert menu.cancel_restores_app is True

    def test_window_target_uses_its_name(self):
        menu = compose_home_menu(WindowTarget(window_id="w1", name="Game"))
        assert menu.entries[0].name == "Game"
        assert menu.cancel_restores_app is True
