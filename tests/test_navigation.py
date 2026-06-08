"""Tests for FocusNavigator — the tile-bar / top-bar focus state machine.

Pure interaction logic over a mocked tilebar/topbar pair and a mock Feedback
port; no Qt. Events are passed as plain strings (StrEnum-compatible).
"""

from unittest.mock import MagicMock

from application.navigation import FocusNavigator


def _make(topbar_count=3):
    tilebar = MagicMock()
    tilebar.move.return_value = True
    topbar = MagicMock()
    topbar.count = topbar_count
    on_tile_menu = MagicMock()
    feedback = MagicMock()
    nav = FocusNavigator(
        tilebar, topbar, on_tile_menu=on_tile_menu, feedback=feedback,
    )
    return nav, tilebar, topbar, on_tile_menu


class TestBasics:
    def test_starts_in_tiles(self):
        nav, *_ = _make()
        assert nav.in_tiles is True


class TestPadInTiles:
    def test_left_moves_tilebar(self):
        nav, tilebar, _, _ = _make()
        nav.handle_pad("left")
        tilebar.move.assert_called_once_with(-1)

    def test_right_moves_tilebar(self):
        nav, tilebar, _, _ = _make()
        nav.handle_pad("right")
        tilebar.move.assert_called_once_with(+1)

    def test_select_activates_current_tile(self):
        nav, tilebar, _, _ = _make()
        nav.handle_pad("select")
        tilebar.select_current.assert_called_once()

    def test_close_opens_tile_menu(self):
        nav, _, _, on_tile_menu = _make()
        nav.handle_pad("close")
        on_tile_menu.assert_called_once()

    def test_up_switches_to_topbar(self):
        nav, _, _, _ = _make(topbar_count=3)
        nav.handle_pad("up")
        assert nav.in_tiles is False

    def test_up_ignored_when_no_topbar_buttons(self):
        nav, _, _, _ = _make(topbar_count=0)
        nav.handle_pad("up")
        assert nav.in_tiles is True


class TestPadInTopbar:
    def _in_topbar(self, topbar_count=3):
        nav, tilebar, topbar, menu = _make(topbar_count)
        nav.handle_pad("up")          # enter topbar at index 0
        return nav, tilebar, topbar, menu

    def test_right_increments_index_modulo(self):
        nav, _, topbar, _ = self._in_topbar(topbar_count=3)
        nav.handle_pad("right")
        nav.handle_pad("select")
        topbar.trigger.assert_called_once_with(1)

    def test_right_wraps_around(self):
        nav, _, topbar, _ = self._in_topbar(topbar_count=2)
        nav.handle_pad("right")
        nav.handle_pad("right")       # 0 → 1 → 0
        nav.handle_pad("select")
        topbar.trigger.assert_called_once_with(0)

    def test_left_wraps_to_last(self):
        nav, _, topbar, _ = self._in_topbar(topbar_count=3)
        nav.handle_pad("left")        # 0 → 2
        nav.handle_pad("select")
        topbar.trigger.assert_called_once_with(2)

    def test_down_returns_to_tiles(self):
        nav, *_ = self._in_topbar()
        nav.handle_pad("down")
        assert nav.in_tiles is True

    def test_cancel_returns_to_tiles(self):
        nav, *_ = self._in_topbar()
        nav.handle_pad("cancel")
        assert nav.in_tiles is True


class TestRenderAndHover:
    def test_render_tiles_highlights_tilebar(self):
        nav, tilebar, topbar, _ = _make()
        nav.render()
        tilebar.set_focused.assert_called_with(True)
        topbar.set_selected.assert_called_with(None)

    def test_render_topbar_highlights_button(self):
        nav, tilebar, topbar, _ = _make()
        nav.handle_pad("up")
        nav.handle_pad("right")       # index 1
        nav.render()
        tilebar.set_focused.assert_called_with(False)
        topbar.set_selected.assert_called_with(1)

    def test_hover_topbar_sets_index(self):
        nav, _, topbar, _ = _make()
        nav.hover_topbar(2)
        nav.handle_pad("select")
        topbar.trigger.assert_called_once_with(2)

    def test_hover_tiles_returns_to_tiles(self):
        nav, *_ = _make()
        nav.handle_pad("up")
        nav.hover_tiles()
        assert nav.in_tiles is True

    def test_focus_topbar_switches_and_renders(self):
        nav, tilebar, topbar, _ = _make()
        nav.focus_topbar()
        assert nav.in_tiles is False
        tilebar.set_focused.assert_called_with(False)
