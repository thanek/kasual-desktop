"""Unit tests for TilePopoverMenu (presentation): the Y-toggle close and the
separator handling of the unified menu (§7.3).

The popover pushes a handler on the gamepad stack and installs an app event
filter; both are torn down on dismiss. Offscreen Qt (conftest) means no real
display is needed.
"""

from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from domain.input.vocabulary import Event
from domain.menu.entry import LAUNCH, MOVE, SEPARATOR
from domain.menu.item import MenuItem
from infrastructure.common.qt.overlays.tile_popover import TilePopoverMenu


def _items():
    # Mirrors compose_tile_menu for an idle app: Launch · ─ · Move.
    return [
        MenuItem("Launch", LAUNCH),
        MenuItem("", SEPARATOR),
        MenuItem("Move", MOVE),
    ]


def _popover(mock_gamepad, on_select=None):
    parent = QWidget()
    pop = TilePopoverMenu(
        items=_items(),
        on_select=on_select or MagicMock(),
        gamepad=mock_gamepad,
        feedback=MagicMock(),
        parent=parent,
    )
    pop._test_parent = parent   # keep the parent alive for the test's duration
    return pop


class TestActionsToggleClose:
    def test_actions_dismisses_the_popover(self, mock_gamepad):
        pop = _popover(mock_gamepad)
        closed = []
        pop.closed.connect(lambda: closed.append(True))
        assert pop._handle_pad in mock_gamepad._stack
        pop._handle_pad(Event.ACTIONS)            # press Y again → toggle closed
        assert closed == [True]
        assert pop._handle_pad not in mock_gamepad._stack

    def test_actions_does_not_select_an_item(self, mock_gamepad):
        on_select = MagicMock()
        pop = _popover(mock_gamepad, on_select=on_select)
        pop._handle_pad(Event.ACTIONS)
        on_select.assert_not_called()


class TestSeparatorNavigation:
    def test_down_skips_separator(self, mock_gamepad):
        pop = _popover(mock_gamepad)
        assert pop._cursor.index == 0          # Launch
        pop._handle_pad(Event.DOWN)            # over the separator → Move
        assert pop._cursor.index == 2

    def test_select_never_lands_on_separator(self, mock_gamepad):
        on_select = MagicMock()
        pop = _popover(mock_gamepad, on_select=on_select)
        pop._handle_pad(Event.DOWN)            # → Move (index 2)
        pop._handle_pad(Event.SELECT)
        assert on_select.call_args[0][0].action == MOVE
