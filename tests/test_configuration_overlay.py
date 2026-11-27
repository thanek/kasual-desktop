"""The Configuration modal and the screen and audio-output choices it offers."""

from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QLabel, QScrollArea

from domain.audio.kasual_output import output_choices
from domain.audio.output import AudioOutput
from domain.display.choices import screen_choices
from domain.display.display import SYSTEM_DECIDES, Display
from domain.input.vocabulary import Event
from domain.navigation import hints
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


class FakeOutputPicker:
    def __init__(self, outputs=(), chosen=SYSTEM_DECIDES):
        self._outputs = list(outputs)
        self._chosen = chosen
        self.choices = []

    def options(self):
        return self._outputs

    def chosen(self):
        return self._chosen

    def choose(self, output_id):
        self.choices.append(output_id)
        self._chosen = output_id


class FakeAutostart:
    def __init__(self, enabled=False, writable=True):
        self._enabled = enabled
        self._writable = writable

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        if self._writable:
            self._enabled = enabled


def _overlay(mock_gamepad, displays, audio_output=None, autostart=None):
    from infrastructure.common.qt.overlays.configuration_overlay import ConfigurationOverlay
    return ConfigurationOverlay(
        mock_gamepad, displays, audio_output or FakeOutputPicker(), MagicMock(),
        autostart=autostart)


def _labels(overlay):
    return [label.text() for label in overlay.findChildren(QLabel)]


def _switch_row(overlay):
    from infrastructure.common.qt.ui.toggle_switch import ToggleSwitch
    return next(row for row in overlay._rows if row.frame.findChild(ToggleSwitch))


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
    def test_the_system_comes_first_then_every_output_with_the_chosen_one_marked(self):
        choices = output_choices(FakeOutputPicker([SPEAKERS, HDMI], chosen="alsa.hdmi"))
        assert [(c.value, c.chosen) for c in choices] == [
            (SYSTEM_DECIDES, False), ("alsa.speaker", False), ("alsa.hdmi", True)]

    def test_an_unplugged_output_is_shown_but_not_pickable(self):
        unplugged = output_choices(FakeOutputPicker([HEADPHONES]))[1]
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
        overlay = _overlay(mock_gamepad, FakeDisplays([*MONITORS, ABSENT]))
        visited = []
        for _ in range(3):
            _press(overlay, Event.DOWN)
            visited.append(overlay._cursor.index)
        assert visited == [1, 2, 2]

    def test_cancel_closes_without_choosing(self, mock_gamepad):
        displays = FakeDisplays(MONITORS)
        overlay = _overlay(mock_gamepad, displays)
        overlay._handle_pad(Event.CANCEL)
        assert displays.choices == []
        assert overlay._handle_pad not in mock_gamepad._stack


class TestAudioSection:
    def test_lists_every_output_under_its_own_heading(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS),
                           FakeOutputPicker([SPEAKERS, HDMI]))
        assert {"Audio output", "USB Audio Speakers", "HDMI Audio"} <= set(_labels(overlay))
        assert _labels(overlay).count("Chosen by the system") == 2

    def test_is_left_out_when_the_system_offers_no_outputs(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        assert "Audio output" not in _labels(overlay)

    def test_picking_an_output_chooses_it_for_kasual_and_leaves_the_screen_alone(
            self, mock_gamepad):
        displays = FakeDisplays(MONITORS)
        outputs = FakeOutputPicker([SPEAKERS, HDMI])
        overlay = _overlay(mock_gamepad, displays, outputs)
        _press(overlay, *[Event.DOWN] * 5, Event.SELECT)
        assert outputs.choices == ["alsa.hdmi"]
        assert displays.choices == []

    def test_picking_the_system_hands_the_choice_back(self, mock_gamepad):
        outputs = FakeOutputPicker([SPEAKERS, HDMI], chosen="alsa.hdmi")
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS), outputs)
        _press(overlay, *[Event.DOWN] * 3, Event.SELECT)
        assert outputs.choices == [SYSTEM_DECIDES]

    def test_skips_an_unplugged_output(self, mock_gamepad):
        outputs = FakeOutputPicker([SPEAKERS, HEADPHONES, HDMI])
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS), outputs)
        _press(overlay, *[Event.DOWN] * 5, Event.SELECT)
        assert outputs.choices == ["alsa.hdmi"]


class TestStartupSection:
    def _switch(self, overlay):
        from infrastructure.common.qt.ui.toggle_switch import ToggleSwitch
        return overlay.findChild(ToggleSwitch)

    def _to_the_switch(self, overlay):
        _press(overlay, *[Event.DOWN] * overlay._rows.index(_switch_row(overlay)))

    def test_is_left_out_where_the_session_cannot_autostart(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        assert "Startup" not in _labels(overlay)

    def test_shows_the_current_state(self, mock_gamepad):
        on = _overlay(mock_gamepad, FakeDisplays(), autostart=FakeAutostart(enabled=True))
        off = _overlay(mock_gamepad, FakeDisplays(), autostart=FakeAutostart())
        assert self._switch(on).isChecked() is True
        assert self._switch(off).isChecked() is False

    def test_selecting_it_flips_it_and_stays_open(self, mock_gamepad):
        autostart, displays = FakeAutostart(), FakeDisplays(MONITORS)
        overlay = _overlay(mock_gamepad, displays, autostart=autostart)
        self._to_the_switch(overlay)
        _press(overlay, Event.SELECT)
        assert autostart.is_enabled() is True
        assert self._switch(overlay).isChecked() is True
        assert overlay._handle_pad in mock_gamepad._stack
        _press(overlay, Event.SELECT)
        assert autostart.is_enabled() is False
        assert displays.choices == []

    def test_clicking_it_flips_it(self, mock_gamepad):
        autostart = FakeAutostart()
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS), autostart=autostart)
        _switch_row(overlay).frame.mousePressEvent(None)
        assert autostart.is_enabled() is True

    def test_a_refused_change_is_not_shown_as_made(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(),
                           autostart=FakeAutostart(writable=False))
        self._to_the_switch(overlay)
        _press(overlay, Event.SELECT)
        assert self._switch(overlay).isChecked() is False


class TestLongLists:
    MANY_SCREENS = [Display(f"DP-{n}", f"Screen {n}") for n in range(6)]
    MANY_OUTPUTS = [AudioOutput(f"alsa.{n}", f"Output {n}") for n in range(8)]

    def _overlay(self, mock_gamepad, qapp, screens, outputs, screen=None, output=None):
        overlay = _overlay(
            mock_gamepad, FakeDisplays(screens, chosen=screen),
            FakeOutputPicker(outputs, chosen=output), autostart=FakeAutostart())
        qapp.processEvents()
        return overlay

    def _fully_visible(self, row):
        return row.frame.visibleRegion().boundingRect().contains(row.frame.rect())

    def _visible_labels(self, overlay):
        return {row.frame.findChildren(QLabel)[-1].text()
                for row in overlay._rows if self._fully_visible(row)}

    def test_short_lists_have_nothing_to_scroll(self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, MONITORS, [SPEAKERS, HDMI])
        assert overlay.findChildren(QScrollArea) == []
        assert all(self._fully_visible(row) for row in overlay._rows)

    def test_each_long_list_shows_three_rows_and_scrolls_on_its_own(
            self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, self.MANY_SCREENS, self.MANY_OUTPUTS)
        assert len(overlay.findChildren(QScrollArea)) == 2
        assert sum(map(self._fully_visible, overlay._rows)) == 3 + 3 + 1

    def test_only_the_long_list_scrolls(self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, MONITORS, self.MANY_OUTPUTS)
        assert len(overlay.findChildren(QScrollArea)) == 1

    def test_the_startup_switch_stays_visible_wherever_the_cursor_is(
            self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, self.MANY_SCREENS, self.MANY_OUTPUTS)
        for _ in overlay._rows:
            assert self._fully_visible(_switch_row(overlay))
            _press(overlay, Event.DOWN)
            qapp.processEvents()

    def test_the_selected_row_is_always_visible(self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, self.MANY_SCREENS, self.MANY_OUTPUTS)
        for event in [Event.DOWN] * len(overlay._rows) + [Event.UP] * len(overlay._rows):
            assert self._fully_visible(overlay._rows[overlay._cursor.index])
            _press(overlay, event)
            qapp.processEvents()

    def test_opens_with_both_choices_in_view(self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, self.MANY_SCREENS, self.MANY_OUTPUTS,
                                screen="DP-5", output="alsa.6")
        assert {"Screen 5", "Output 6"} <= self._visible_labels(overlay)

    def test_coming_back_keeps_the_selected_row_in_view(self, mock_gamepad, qapp):
        overlay = self._overlay(mock_gamepad, qapp, self.MANY_SCREENS, self.MANY_OUTPUTS,
                                screen="DP-5")
        _press(overlay, *[Event.UP] * len(overlay._rows))
        overlay.hide()
        overlay.show()
        qapp.processEvents()
        assert "Chosen by the system" in self._visible_labels(overlay)
        assert self._fully_visible(overlay._rows[0])


class TestSectionSwitching:
    SYSTEM_SCREEN, DELL, LG, SYSTEM_OUTPUT, USB, HDMI_ROW, STARTUP = range(7)

    def _overlay(self, mock_gamepad, screen=None, output=None, outputs=(SPEAKERS, HDMI)):
        return _overlay(
            mock_gamepad, FakeDisplays(MONITORS, chosen=screen),
            FakeOutputPicker(outputs, chosen=output), autostart=FakeAutostart())

    def test_jumps_forward_through_every_section_onto_what_is_chosen(self, mock_gamepad):
        overlay = self._overlay(mock_gamepad, output="alsa.hdmi")
        visited = []
        for _ in range(3):
            _press(overlay, Event.SECTION_NEXT)
            visited.append(overlay._cursor.index)
        assert visited == [self.HDMI_ROW, self.STARTUP, self.STARTUP]

    def test_jumps_back_and_stops_at_the_first_section(self, mock_gamepad):
        overlay = self._overlay(mock_gamepad)
        _press(overlay, *[Event.SECTION_NEXT] * 2)
        visited = []
        for _ in range(3):
            _press(overlay, Event.SECTION_PREV)
            visited.append(overlay._cursor.index)
        assert visited == [self.SYSTEM_OUTPUT, self.SYSTEM_SCREEN, self.SYSTEM_SCREEN]

    def test_returns_to_the_row_it_left(self, mock_gamepad):
        overlay = self._overlay(mock_gamepad)
        _press(overlay, Event.DOWN, Event.SECTION_NEXT, Event.SECTION_PREV)
        assert overlay._cursor.index == self.DELL

    def test_never_lands_on_an_unplugged_output(self, mock_gamepad):
        overlay = self._overlay(
            mock_gamepad, output=HEADPHONES.id, outputs=(HEADPHONES, HDMI))
        _press(overlay, Event.SECTION_NEXT)
        assert overlay._cursor.index == self.SYSTEM_OUTPUT

    def test_staying_put_makes_no_sound(self, mock_gamepad):
        overlay = self._overlay(mock_gamepad)
        overlay._feedback.reset_mock()
        _press(overlay, Event.SECTION_PREV)
        overlay._feedback.play.assert_not_called()

    def test_a_single_section_has_nowhere_to_jump(self, mock_gamepad):
        overlay = _overlay(mock_gamepad, FakeDisplays(MONITORS))
        _press(overlay, Event.SECTION_NEXT, Event.SECTION_PREV)
        assert overlay._cursor.index == self.SYSTEM_SCREEN

    def test_brackets_stand_in_for_the_bumpers(self, mock_gamepad):
        overlay = self._overlay(mock_gamepad)
        visited = []
        for key in (Qt.Key.Key_BracketRight, Qt.Key.Key_BracketLeft):
            overlay.keyPressEvent(QKeyEvent(
                QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
            visited.append(overlay._cursor.index)
        assert visited == [self.SYSTEM_OUTPUT, self.SYSTEM_SCREEN]

    def test_the_hint_bar_mentions_the_bumpers(self):
        assert [hint.button for hint in hints.CONFIGURATION.bumpers] == [
            hints.Button.LB, hints.Button.RB]
