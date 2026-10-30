"""The Configuration modal and the screen choices it shares with the tray menu."""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QLabel

from domain.display.choices import screen_choices
from domain.display.display import SYSTEM_DECIDES, Display
from domain.input.vocabulary import Event
from domain.system.actions import CONFIGURATION, ActionDeps
from domain.system.runner import ActionRunner

MONITORS = [Display("DP-1", "Dell (DP-1)"), Display("HDMI-A-1", "LG TV (HDMI-A-1)")]
ABSENT = Display("DP-3", "DP-3", connected=False)


class FakeDisplays:
    def __init__(self, options=(), chosen=SYSTEM_DECIDES):
        self._options = list(options)
        self._chosen = chosen
        self.choices = []

    def options(self):
        return self._options

    def chosen(self):
        return self._chosen

    def choose(self, display_id):
        self.choices.append(display_id)
        self._chosen = display_id


def _overlay(mock_gamepad, displays):
    from infrastructure.common.qt.overlays.configuration_overlay import ConfigurationOverlay
    return ConfigurationOverlay(mock_gamepad, displays, MagicMock())


class TestScreenChoices:
    def test_the_system_comes_first_then_every_screen(self):
        choices = screen_choices(FakeDisplays(MONITORS))
        assert [c.display_id for c in choices] == [SYSTEM_DECIDES, "DP-1", "HDMI-A-1"]

    def test_marks_only_the_chosen_screen(self):
        choices = screen_choices(FakeDisplays(MONITORS, chosen="HDMI-A-1"))
        assert [c.chosen for c in choices] == [False, False, True]

    def test_a_remembered_absent_screen_is_shown_but_not_pickable(self):
        absent = screen_choices(FakeDisplays([*MONITORS, ABSENT], chosen="DP-3"))[-1]
        assert (absent.chosen, absent.pickable) == (True, False)
        assert "DP-3" in absent.label


class TestConfigurationAction:
    def test_opens_the_configuration_overlay(self):
        desktop = MagicMock()
        ActionRunner(ActionDeps(desktop=desktop, power=MagicMock()),
                     confirm=MagicMock()).run(CONFIGURATION)
        desktop.open_configuration_overlay.assert_called_once_with()


class TestConfigurationOverlay:
    def test_lists_every_screen_choice(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        texts = [label.text() for label in overlay.findChildren(QLabel)]
        assert {"Chosen by the system", "Dell (DP-1)", "LG TV (HDMI-A-1)"} <= set(texts)

    def test_starts_on_the_chosen_screen(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS, chosen="HDMI-A-1"))
        assert overlay._cursor.index == 2

    def test_picking_a_screen_chooses_it_and_closes(self, mock_gamepad):
        displays = FakeDisplays(MONITORS)
        overlay = _overlay(mock_gamepad, displays)
        closed = []
        overlay.closed.connect(lambda: closed.append(True))
        overlay._handle_pad(Event.DOWN)
        overlay._handle_pad(Event.SELECT)
        assert displays.choices == ["DP-1"]
        assert closed == [True]

    def test_picking_the_system_chooses_no_screen(self, mock_gamepad):
        displays = FakeDisplays(MONITORS, chosen="DP-1")
        overlay = _overlay(mock_gamepad, displays)
        overlay._handle_pad(Event.UP)
        overlay._handle_pad(Event.SELECT)
        assert displays.choices == [SYSTEM_DECIDES]

    def test_skips_a_screen_that_is_not_connected(self, mock_gamepad):
        displays = FakeDisplays([*MONITORS, ABSENT])
        overlay = _overlay(mock_gamepad, displays)
        for _ in range(4):
            overlay._handle_pad(Event.DOWN)
        overlay._handle_pad(Event.SELECT)
        assert displays.choices == ["HDMI-A-1"]

    def test_cancel_closes_without_choosing(self, mock_gamepad):
        displays = FakeDisplays(MONITORS)
        overlay = _overlay(mock_gamepad, displays)
        overlay._handle_pad(Event.CANCEL)
        assert displays.choices == []
        assert overlay._handle_pad not in mock_gamepad._stack
