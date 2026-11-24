"""Unit tests for TileSettings — the tile settings overlay that applies every pick at once."""

from unittest.mock import MagicMock

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
import pytest

from domain.input.vocabulary import Event, Trigger
from infrastructure.common.qt.overlays.tile_settings import TileSettings, _Group

COLORS = ["#aaaaaa", "#bbbbbb", "#cccccc", "#dddddd"]
TWO_ROWS = [f"#{i:02x}{i:02x}{i:02x}" for i in range(12)]


def _make(mock_gamepad, colors=COLORS, color="#aaaaaa", trigger=Trigger.CLICK,
          on_color_changed=None, on_trigger_changed=None, on_closed=None):
    return TileSettings(
        app_name="Steam",
        colors=colors,
        color=color,
        trigger=trigger,
        on_color_changed=on_color_changed or MagicMock(),
        on_trigger_changed=on_trigger_changed or MagicMock(),
        on_closed=on_closed or MagicMock(),
        gamepad=mock_gamepad,
        feedback=MagicMock(),
    )


def _press(overlay, *events):
    for event in events:
        overlay._handle_pad(event)


def _go_to_colors(overlay):
    _press(overlay, Event.SECTION_NEXT)


def _go_to_close_button(overlay):
    _press(overlay, Event.SECTION_NEXT, Event.SECTION_NEXT)


class TestChoosingColor:
    def test_select_applies_the_color_at_once(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.RIGHT, Event.SELECT)
        on_color.assert_called_once_with("#bbbbbb")

    def test_moving_the_cursor_applies_nothing(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.RIGHT)
        on_color.assert_not_called()

    def test_choosing_the_current_color_applies_nothing(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.SELECT)
        on_color.assert_not_called()

    def test_the_previous_color_can_be_chosen_back(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.RIGHT, Event.SELECT, Event.LEFT, Event.SELECT)
        assert [c.args for c in on_color.call_args_list] == [("#bbbbbb",), ("#aaaaaa",)]

    def test_left_wraps_to_the_last_color(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.LEFT, Event.SELECT)
        on_color.assert_called_once_with("#dddddd")

    def test_a_color_outside_the_palette_starts_at_the_first_swatch(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, color="#e50914", on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.SELECT)
        on_color.assert_called_once_with("#aaaaaa")

    def test_clicking_a_swatch_applies_it(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        overlay._swatches[2].click()
        on_color.assert_called_once_with("#cccccc")


class TestChoosingRecallTrigger:
    def test_moving_to_the_other_option_applies_it_at_once(self, mock_gamepad):
        on_trigger = MagicMock()
        overlay = _make(mock_gamepad, on_trigger_changed=on_trigger)
        _press(overlay, Event.RIGHT)
        on_trigger.assert_called_once_with(Trigger.HOLD_1S)

    def test_selecting_the_current_option_applies_nothing(self, mock_gamepad):
        on_trigger = MagicMock()
        overlay = _make(mock_gamepad, on_trigger_changed=on_trigger)
        _press(overlay, Event.SELECT)
        on_trigger.assert_not_called()

    def test_clicking_an_option_applies_it(self, mock_gamepad):
        on_trigger = MagicMock()
        overlay = _make(mock_gamepad, trigger=Trigger.HOLD_1S, on_trigger_changed=on_trigger)
        overlay._recall_buttons[0].click()
        on_trigger.assert_called_once_with(Trigger.CLICK)

    def test_changing_the_trigger_leaves_the_color_alone(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _press(overlay, Event.RIGHT)
        on_color.assert_not_called()


class TestNavigation:
    def test_starts_on_the_recall_section(self, mock_gamepad):
        assert _make(mock_gamepad)._active_group == _Group.RECALL

    @pytest.mark.parametrize("events, expected", [
        ([Event.SECTION_NEXT], _Group.COLOR),
        ([Event.SECTION_NEXT, Event.SECTION_PREV], _Group.RECALL),
        ([Event.SECTION_NEXT] * 2, _Group.CLOSE),
        ([Event.SECTION_NEXT] * 3, _Group.CLOSE),
        ([Event.SECTION_PREV], _Group.RECALL),
        ([Event.UP], _Group.RECALL),
        ([Event.DOWN], _Group.COLOR),
        ([Event.DOWN, Event.UP], _Group.RECALL),
        ([Event.DOWN, Event.DOWN], _Group.CLOSE),
        ([Event.DOWN, Event.DOWN, Event.UP], _Group.COLOR),
        ([Event.DOWN, Event.DOWN, Event.DOWN], _Group.CLOSE),
    ])
    def test_sections(self, mock_gamepad, events, expected):
        overlay = _make(mock_gamepad)
        _press(overlay, *events)
        assert overlay._active_group == expected

    def test_down_stays_in_the_grid_until_its_last_row(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, colors=TWO_ROWS, color=TWO_ROWS[0],
                        on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.DOWN, Event.SELECT)
        on_color.assert_called_once_with(TWO_ROWS[10])
        _press(overlay, Event.DOWN)
        assert overlay._active_group == _Group.CLOSE


def _close_with_b(overlay):
    _press(overlay, Event.CANCEL)


def _close_with_the_button(overlay):
    _go_to_close_button(overlay)
    _press(overlay, Event.SELECT)


def _close_with_a_click_on_the_button(overlay):
    overlay._btn_close.click()


def _close_with_a_click_outside(overlay):
    overlay._on_outside_click()


def _close_with_escape(overlay):
    overlay.keyPressEvent(QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))


class TestClosing:
    def test_takes_the_pad_while_open(self, mock_gamepad):
        overlay = _make(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._stack

    @pytest.mark.parametrize("close", [
        _close_with_b, _close_with_the_button, _close_with_a_click_on_the_button,
        _close_with_a_click_outside, _close_with_escape,
    ])
    def test_closes_once_and_gives_the_pad_back(self, mock_gamepad, close):
        on_closed = MagicMock()
        overlay = _make(mock_gamepad, on_closed=on_closed)
        close(overlay)
        on_closed.assert_called_once_with()
        assert overlay._handle_pad not in mock_gamepad._stack

    def test_closing_does_not_undo_the_chosen_color(self, mock_gamepad):
        on_color = MagicMock()
        overlay = _make(mock_gamepad, on_color_changed=on_color)
        _go_to_colors(overlay)
        _press(overlay, Event.RIGHT, Event.SELECT, Event.CANCEL)
        on_color.assert_called_once_with("#bbbbbb")

    def test_group_cancel_gives_the_pad_back_without_callbacks(self, mock_gamepad):
        on_closed = MagicMock()
        overlay = _make(mock_gamepad, on_closed=on_closed)
        overlay.cancel()
        assert overlay._handle_pad not in mock_gamepad._stack
        on_closed.assert_not_called()
