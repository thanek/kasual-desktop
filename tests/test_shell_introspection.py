"""The read model the behavioral harness asserts against (KD_TEST_API=1).

An open menu needs a layer-shell surface, which no unit test has; that path is covered
by the `minimize` behavioral scenario, which reads this very snapshot back.
"""

from unittest.mock import MagicMock, patch

from domain.menu.entry import RETURN_TO_DESKTOP
from domain.catalog.window import Window
from domain.shell.introspection import (
    HomeMenuSnapshot, MenuItemSnapshot, MenuSectionSnapshot,
)
from domain.system.actions import HIDE_DESKTOP
from test_desktop_lifecycle import _make_desktop


def _cards(*focused_action: str) -> HomeMenuSnapshot:
    return HomeMenuSnapshot(
        open=True,
        sections=(
            MenuSectionSnapshot(
                kind='actions', columns=1,
                items=tuple(
                    MenuItemSnapshot(label=action, action=action,
                                     focused=action in focused_action)
                    for action in (HIDE_DESKTOP, RETURN_TO_DESKTOP)
                ),
            ),
        ),
    )


class TestFocusedItem:
    """Which card the cursor sits on decides what a press of A does, so the harness
    reads it rather than assuming the menu opened where it always used to."""

    def test_finds_the_focused_card(self):
        assert _cards(HIDE_DESKTOP).focused.action == HIDE_DESKTOP

    def test_no_focus_is_an_answer(self):
        assert _cards().focused is None


class TestSnapshot:
    def test_a_closed_menu_offers_nothing(self, mock_gamepad):
        menu = _make_desktop(mock_gamepad).snapshot().home_menu
        assert not menu.open
        assert menu.sections == ()

    def test_the_foreground_app_is_the_one_the_shell_believes_in(self, mock_gamepad):
        """Not the one whose process is alive: the shell's belief is what makes it
        return to the Home screen, and it outlives the app it was about."""
        desktop = _make_desktop(mock_gamepad)
        assert desktop.snapshot().foreground is None

        running = MagicMock()
        running.name = 'Kingdom Come Deliverance'
        with patch.object(desktop.app_control, 'current_app', return_value=running):
            assert desktop.snapshot().foreground == 'Kingdom Come Deliverance'


class TestTileCursor:
    """`tile_index` describes an app tile and is None everywhere else, so on its own
    it cannot tell a cursor parked on a window tile from no focus at all. The
    behavioral harness read that as "before the target" and pressed right — away
    from the app tiles, which are the leftmost section — until the bar ran out.

    The app-tile case needs a populated bar; it is covered in test_tile_bar.py.
    """

    def _desktop_with_a_window_tile(self, mock_gamepad):
        desktop = _make_desktop(mock_gamepad)
        desktop._tilebar.update_windows(
            [Window(id='w1', title='Brave', pid=0, resource_class='brave-browser')])
        return desktop

    def test_a_window_tile_still_reports_where_the_cursor_is(self, mock_gamepad):
        desktop = self._desktop_with_a_window_tile(mock_gamepad)
        cursor = len(desktop._tilebar._tiles) + 1        # past the apps and the [+]
        desktop._tilebar._tile_index = cursor
        focus = desktop.snapshot().focus

        assert focus.tile_index is None                  # no app tile to name
        assert (focus.cursor, focus.kind) == (cursor, 'window')

    def test_the_add_tile_is_distinguishable_from_a_window_tile(self, mock_gamepad):
        desktop = self._desktop_with_a_window_tile(mock_gamepad)
        desktop._tilebar._tile_index = len(desktop._tilebar._tiles)
        focus = desktop.snapshot().focus
        assert (focus.kind, focus.tile_index) == ('add', None)

    def test_the_cursor_orders_the_bar_left_to_right(self, mock_gamepad):
        """What makes navigation decidable: anything that is not an app tile has a
        cursor greater than every app tile's."""
        desktop = self._desktop_with_a_window_tile(mock_gamepad)
        kinds = []
        for i in range(desktop._tilebar._total()):
            desktop._tilebar._tile_index = i
            kinds.append(desktop.snapshot().focus.kind)
        assert kinds == ['app'] * len(desktop._tilebar._tiles) + ['add', 'window']

    def test_the_header_zone_has_no_tile_cursor(self, mock_gamepad):
        desktop = self._desktop_with_a_window_tile(mock_gamepad)
        with patch.object(type(desktop._nav), 'in_tiles',
                          property(lambda _self: False)):
            focus = desktop.snapshot().focus
        assert focus.zone == 'header'
        assert (focus.cursor, focus.kind) == (None, None)
