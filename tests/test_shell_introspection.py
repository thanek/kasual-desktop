"""The read model the behavioral harness asserts against (KD_TEST_API=1).

An open menu needs a layer-shell surface, which no unit test has; that path is covered
by the `minimize` behavioral scenario, which reads this very snapshot back.
"""

from unittest.mock import MagicMock, patch

from domain.catalog.app import App
from domain.catalog.window import Window
from test_desktop_lifecycle import _make_desktop


class TestSnapshot:
    def test_a_closed_menu_offers_nothing(self, mock_gamepad):
        menu = _make_desktop(mock_gamepad).snapshot().home_menu
        assert not menu.open
        assert menu.sections == ()

    def test_a_closed_tile_popover_offers_nothing(self, mock_gamepad):
        menu = _make_desktop(mock_gamepad).snapshot().tile_menu
        assert not menu.open
        assert menu.items == ()

    def test_a_tile_reports_whether_its_app_is_running(self, mock_gamepad):
        """What the popover is composed from — Restore/Close against Launch — so a
        tile that misreads its own state offers the wrong way out."""
        desktop = _make_desktop(
            mock_gamepad, apps=[App(name='File Browser', command='files', id='files')])

        assert desktop.snapshot().tiles[0].running is False
        with patch.object(desktop._tilebar, 'is_tile_running',
                          side_effect=lambda idx, _windows: idx == 0):
            assert desktop.snapshot().tiles[0].running is True

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
