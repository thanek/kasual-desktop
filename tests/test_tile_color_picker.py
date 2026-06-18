"""Unit tests for TileColorPicker — the palette overlay.

Created offscreen (showFullScreen needs no real display). Covers pad handler
registration, left/right navigation, select → on_select(colour), cancel paths,
and the group cancel().
"""

from unittest.mock import MagicMock

from infrastructure.qt.overlays.tile_color_picker import TileColorPicker

COLORS = ["#aaaaaa", "#bbbbbb", "#cccccc", "#dddddd"]


def _make(mock_gamepad, selected=None, on_select=None, on_cancel=None):
    return TileColorPicker(
        colors=COLORS,
        selected=selected,
        on_select=on_select or (lambda c: None),
        on_cancel=on_cancel or (lambda: None),
        gamepad=mock_gamepad,
        feedback=MagicMock(),
    )


class TestHandlerRegistration:
    def test_registers_handler_on_init(self, mock_gamepad):
        picker = _make(mock_gamepad)
        assert picker._handle_pad in mock_gamepad._stack

    def test_deregisters_after_select(self, mock_gamepad):
        picker = _make(mock_gamepad)
        picker._handle_pad("select")
        assert picker._handle_pad not in mock_gamepad._stack

    def test_deregisters_after_cancel(self, mock_gamepad):
        picker = _make(mock_gamepad)
        picker._handle_pad("cancel")
        assert picker._handle_pad not in mock_gamepad._stack


class TestSelection:
    def test_starts_on_selected_color(self, mock_gamepad):
        chosen = []
        picker = _make(mock_gamepad, selected="#cccccc", on_select=chosen.append)
        picker._handle_pad("select")
        assert chosen == ["#cccccc"]

    def test_defaults_to_first_when_selected_absent(self, mock_gamepad):
        chosen = []
        picker = _make(mock_gamepad, selected="#nope", on_select=chosen.append)
        picker._handle_pad("select")
        assert chosen == ["#aaaaaa"]

    def test_right_moves_to_next_color(self, mock_gamepad):
        chosen = []
        picker = _make(mock_gamepad, selected="#aaaaaa", on_select=chosen.append)
        picker._handle_pad("right")
        picker._handle_pad("select")
        assert chosen == ["#bbbbbb"]

    def test_left_wraps_to_last_color(self, mock_gamepad):
        chosen = []
        picker = _make(mock_gamepad, selected="#aaaaaa", on_select=chosen.append)
        picker._handle_pad("left")
        picker._handle_pad("select")
        assert chosen == ["#dddddd"]


class TestGridNavigation:
    """A palette wider than one row is laid out and navigated as a grid."""

    # 12 colours → rows of 10 + 2 (max 10 per row).
    WIDE = [f"#{i:02x}{i:02x}{i:02x}" for i in range(12)]

    def _make_wide(self, mock_gamepad, selected=None, on_select=None):
        return TileColorPicker(
            colors=self.WIDE,
            selected=selected,
            on_select=on_select or (lambda c: None),
            on_cancel=lambda: None,
            gamepad=mock_gamepad,
            feedback=MagicMock(),
        )

    def test_wraps_into_rows_of_ten(self, mock_gamepad):
        from infrastructure.qt.overlays.tile_color_picker import _MAX_PER_ROW
        picker = self._make_wide(mock_gamepad)
        # The 11th swatch (index 10) starts the second grid row.
        assert len(picker._swatches) == 12
        assert _MAX_PER_ROW == 10

    def test_down_moves_one_row(self, mock_gamepad):
        chosen = []
        picker = self._make_wide(mock_gamepad, selected=self.WIDE[0], on_select=chosen.append)
        picker._handle_pad("down")
        picker._handle_pad("select")
        assert chosen == [self.WIDE[10]]      # column 0 of the second row

    def test_up_wraps_back_down_to_second_row(self, mock_gamepad):
        chosen = []
        picker = self._make_wide(mock_gamepad, selected=self.WIDE[1], on_select=chosen.append)
        picker._handle_pad("up")              # row 0 → wraps to bottom row, col 1
        picker._handle_pad("select")
        assert chosen == [self.WIDE[11]]


class TestCancel:
    def test_cancel_calls_on_cancel_not_on_select(self, mock_gamepad):
        chosen, cancelled = [], []
        picker = _make(mock_gamepad, on_select=chosen.append,
                       on_cancel=lambda: cancelled.append(True))
        picker._handle_pad("cancel")
        assert cancelled == [True]
        assert chosen == []

    def test_group_cancel_deregisters_without_callbacks(self, mock_gamepad):
        chosen, cancelled = [], []
        picker = _make(mock_gamepad, on_select=chosen.append,
                       on_cancel=lambda: cancelled.append(True))
        picker.cancel()
        assert picker._handle_pad not in mock_gamepad._stack
        assert chosen == [] and cancelled == []

    def test_outside_click_cancels(self, mock_gamepad):
        cancelled = []
        picker = _make(mock_gamepad, on_cancel=lambda: cancelled.append(True))
        picker._on_outside_click()
        assert cancelled == [True]
