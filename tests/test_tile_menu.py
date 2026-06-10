"""Tests for compose_tile_menu — the tile Popover composition rule (pure, no Qt)."""

from domain.menu.entry import CLOSE, LAUNCH, RESTORE
from domain.menu.tile import compose_tile_menu
from domain.catalog.target import AppTarget, WindowTarget


class TestCompose:
    def test_app_not_running_offers_launch(self):
        entries = compose_tile_menu(AppTarget(0, "Steam"), is_running=False)
        assert [e.kind for e in entries] == [LAUNCH]

    def test_app_running_offers_restore_and_close(self):
        entries = compose_tile_menu(AppTarget(0, "Steam"), is_running=True)
        assert [e.kind for e in entries] == [RESTORE, CLOSE]

    def test_window_always_offers_restore_and_close(self):
        # An open window is running by definition; is_running is irrelevant.
        entries = compose_tile_menu(WindowTarget("w1", "Firefox"), is_running=False)
        assert [e.kind for e in entries] == [RESTORE, CLOSE]
