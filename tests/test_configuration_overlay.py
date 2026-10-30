"""The Configuration modal and the screen and audio-output choices it offers."""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QLabel

from domain.audio.output import AudioOutput, output_choices
from domain.display.choices import screen_choices
from domain.display.display import SYSTEM_DECIDES, Display
from domain.input.vocabulary import Event
from domain.system.actions import CONFIGURATION, ActionDeps
from domain.system.runner import ActionRunner

MONITORS = [Display("DP-1", "Dell (DP-1)"), Display("HDMI-A-1", "LG TV (HDMI-A-1)")]
ABSENT = Display("DP-3", "DP-3", connected=False)
SPEAKERS = AudioOutput("alsa.speaker", "USB Audio Speakers")
HDMI = AudioOutput("alsa.hdmi", "HDMI Audio")
HEADPHONES = AudioOutput("alsa.headphones", "USB Audio Front Headphones", connected=False)


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


class FakeAudioOutputs:
    def __init__(self, outputs=(), active=None):
        self._outputs = list(outputs)
        self._active = active
        self.activated = []

    def available(self):
        return self._outputs

    def active(self):
        return self._active

    def activate(self, output_id):
        self.activated.append(output_id)
        self._active = output_id


def _overlay(mock_gamepad, displays, audio_outputs=None):
    from infrastructure.common.qt.overlays.configuration_overlay import ConfigurationOverlay
    return ConfigurationOverlay(
        mock_gamepad, displays, audio_outputs or FakeAudioOutputs(), MagicMock())


def _labels(overlay):
    return [label.text() for label in overlay.findChildren(QLabel)]


def _press(overlay, *events):
    for event in events:
        overlay._handle_pad(event)


class TestScreenChoices:
    def test_the_system_comes_first_then_every_screen(self):
        choices = screen_choices(FakeDisplays(MONITORS))
        assert [c.value for c in choices] == [SYSTEM_DECIDES, "DP-1", "HDMI-A-1"]

    def test_marks_only_the_chosen_screen(self):
        choices = screen_choices(FakeDisplays(MONITORS, chosen="HDMI-A-1"))
        assert [c.chosen for c in choices] == [False, False, True]

    def test_a_remembered_absent_screen_is_shown_but_not_pickable(self):
        absent = screen_choices(FakeDisplays([*MONITORS, ABSENT], chosen="DP-3"))[-1]
        assert (absent.chosen, absent.pickable) == (True, False)
        assert "DP-3" in absent.label


class TestOutputChoices:
    def test_offers_every_output_and_marks_the_active_one(self):
        choices = output_choices(FakeAudioOutputs([SPEAKERS, HDMI], active="alsa.hdmi"))
        assert [(c.value, c.chosen) for c in choices] == [
            ("alsa.speaker", False), ("alsa.hdmi", True)]

    def test_an_unplugged_output_is_shown_but_not_pickable(self):
        unplugged = output_choices(FakeAudioOutputs([HEADPHONES]))[0]
        assert unplugged.pickable is False
        assert "Headphones" in unplugged.label


class TestConfigurationAction:
    def test_opens_the_configuration_overlay(self):
        desktop = MagicMock()
        ActionRunner(ActionDeps(desktop=desktop, power=MagicMock()),
                     confirm=MagicMock()).run(CONFIGURATION)
        desktop.open_configuration_overlay.assert_called_once_with()


class TestConfigurationOverlay:
    def test_lists_every_screen_choice(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        assert {"Chosen by the system", "Dell (DP-1)", "LG TV (HDMI-A-1)"} <= set(_labels(overlay))

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


class TestAudioSection:
    def test_lists_every_output_under_its_own_heading(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS),
                           FakeAudioOutputs([SPEAKERS, HDMI]))
        assert {"Audio output", "USB Audio Speakers", "HDMI Audio"} <= set(_labels(overlay))

    def test_is_left_out_when_the_system_offers_no_outputs(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        assert "Audio output" not in _labels(overlay)

    def test_picking_an_output_activates_it_and_leaves_the_screen_alone(self, mock_gamepad):
        displays = FakeDisplays(MONITORS)
        outputs = FakeAudioOutputs([SPEAKERS, HDMI], active="alsa.speaker")
        overlay = _overlay(mock_gamepad, displays, outputs)
        _press(overlay, Event.DOWN, Event.DOWN, Event.DOWN, Event.DOWN, Event.SELECT)
        assert outputs.activated == ["alsa.hdmi"]
        assert displays.choices == []

    def test_skips_an_unplugged_output(self, mock_gamepad):
        outputs = FakeAudioOutputs([SPEAKERS, HEADPHONES, HDMI])
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS), outputs)
        _press(overlay, *[Event.DOWN] * 5, Event.SELECT)
        assert outputs.activated == ["alsa.hdmi"]
