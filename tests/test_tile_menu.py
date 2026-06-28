"""Tests for the tile Popover composition rules (pure, no Qt)."""

from domain.menu.entry import (
    CHANGE_COLOR, CLOSE, LAUNCH, MOVE, PIN, RESTORE, SEPARATOR, UNPIN,
)
from domain.menu.tile import (
    compose_tile_menu, compose_tile_menu_v2, tile_management_menu, tile_menu_v2_for,
)
from domain.catalog.target import AppTarget, WindowTarget


class TestCompose:
    def test_app_not_running_offers_launch(self):
        items = compose_tile_menu(AppTarget(0, "Steam"), is_running=False)
        assert [i.action for i in items] == [LAUNCH]

    def test_app_running_offers_restore_and_close(self):
        items = compose_tile_menu(AppTarget(0, "Steam"), is_running=True)
        assert [i.action for i in items] == [RESTORE, CLOSE]

    def test_window_always_offers_restore_and_close(self):
        # An open window is running by definition; is_running is irrelevant.
        items = compose_tile_menu(WindowTarget("w1", "Firefox"), is_running=False)
        assert [i.action for i in items] == [RESTORE, CLOSE]

    def test_items_carry_their_target(self):
        target = AppTarget(0, "Steam")
        items = compose_tile_menu(target, is_running=True)
        assert all(i.target == target for i in items)


class TestComposeV2:
    """The single, state-dependent v2 menu (§7.3): lifecycle on top, then —
    unless the app is running — a separator and the management group."""

    def test_idle_app_has_launch_separator_then_management(self):
        items = compose_tile_menu_v2(AppTarget(0, "Steam"), is_running=False)
        assert [i.action for i in items] == [LAUNCH, SEPARATOR, MOVE, CHANGE_COLOR, UNPIN]

    def test_running_app_hides_management(self):
        items = compose_tile_menu_v2(AppTarget(0, "Steam"), is_running=True)
        assert [i.action for i in items] == [RESTORE, CLOSE]
        assert SEPARATOR not in [i.action for i in items]

    def test_window_offers_restore_close_separator_pin(self):
        items = compose_tile_menu_v2(WindowTarget("w1", "Firefox"), is_running=True)
        assert [i.action for i in items] == [RESTORE, CLOSE, SEPARATOR, PIN]

    def test_separator_is_not_selectable_payload(self):
        items = compose_tile_menu_v2(AppTarget(0, "Steam"), is_running=False)
        sep = next(i for i in items if i.action == SEPARATOR)
        assert sep.target is None and sep.label == ""


class TestTileMenuV2For:
    """tile_menu_v2_for resolves the running-state rule (the bit that used to live
    in the Qt widget): query only for an AppTarget; a window is always running."""

    def test_app_queries_is_running_by_index(self):
        calls = []
        def is_running(idx):
            calls.append(idx)
            return False
        items = tile_menu_v2_for(AppTarget(3, "Steam"), is_running)
        assert calls == [3]
        assert [i.action for i in items] == [LAUNCH, SEPARATOR, MOVE, CHANGE_COLOR, UNPIN]

    def test_app_running_offers_restore_and_close_only(self):
        items = tile_menu_v2_for(AppTarget(0, "Steam"), lambda idx: True)
        assert [i.action for i in items] == [RESTORE, CLOSE]

    def test_window_never_queries_and_is_running(self):
        called = False
        def is_running(idx):
            nonlocal called
            called = True
            return False
        items = tile_menu_v2_for(WindowTarget("w1", "Firefox"), is_running)
        assert called is False
        assert [i.action for i in items] == [RESTORE, CLOSE, SEPARATOR, PIN]


class TestTileManagementMenu:
    def test_app_tile_offers_move_change_color_and_unpin(self):
        items = tile_management_menu(AppTarget(0, "Steam"))
        assert [i.action for i in items] == [MOVE, CHANGE_COLOR, UNPIN]

    def test_window_tile_offers_pin(self):
        items = tile_management_menu(WindowTarget("w1", "Firefox"))
        assert [i.action for i in items] == [PIN]

    def test_items_carry_target(self):
        target = AppTarget(2, "Steam")
        items = tile_management_menu(target)
        assert all(i.target == target for i in items)

    def test_pin_item_carries_window_target(self):
        target = WindowTarget("w1", "Firefox")
        items = tile_management_menu(target)
        assert all(i.target == target for i in items)
