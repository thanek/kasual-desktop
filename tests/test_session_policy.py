"""Tests for SessionPolicy — controller-presence → desktop-visibility rule.

Pure use-case over fakes; no Qt.
"""

from domain.shell.session import SessionPolicy


class FakeView:
    def __init__(self):
        self.resumed = 0
        self.hidden = 0

    def resume(self):
        self.resumed += 1

    def withdraw(self):
        self.hidden += 1


class FakeIndicator:
    def __init__(self):
        self.states: list[bool] = []

    def set_connected(self, connected: bool):
        self.states.append(connected)


class FakeOverlay:
    def __init__(self):
        self.dismissed = 0

    def hide_overlay(self):
        self.dismissed += 1


class FakeSound:
    def __init__(self):
        self.steps: list[str] = []

    def take_over(self):
        self.steps.append("take_over")

    def give_back(self):
        self.steps.append("give_back")


def _make(sound=None):
    view = FakeView()
    indicator = FakeIndicator()
    return SessionPolicy(view, indicator, sound or FakeSound()), view, indicator


class TestSound:
    def test_a_connected_controller_takes_the_sound_over(self):
        sound = FakeSound()
        policy, _, _ = _make(sound)
        policy.gamepad_connected_changed(True, overlay=None)
        assert sound.steps == ["take_over"]

    def test_a_lost_controller_gives_the_sound_back(self):
        sound = FakeSound()
        policy, _, _ = _make(sound)
        policy.gamepad_connected_changed(False, overlay=None)
        assert sound.steps == ["give_back"]


class TestConnected:
    def test_resumes_desktop(self):
        policy, view, indicator = _make()
        policy.gamepad_connected_changed(True, overlay=None)
        assert view.resumed == 1
        assert view.hidden == 0
        assert indicator.states == [True]

    def test_does_not_touch_overlay(self):
        policy, _, _ = _make()
        overlay = FakeOverlay()
        policy.gamepad_connected_changed(True, overlay=overlay)
        assert overlay.dismissed == 0


class TestDisconnected:
    def test_hides_desktop(self):
        policy, view, indicator = _make()
        policy.gamepad_connected_changed(False, overlay=None)
        assert view.hidden == 1
        assert view.resumed == 0
        assert indicator.states == [False]

    def test_dismisses_open_overlay(self):
        policy, view, _ = _make()
        overlay = FakeOverlay()
        policy.gamepad_connected_changed(False, overlay=overlay)
        assert overlay.dismissed == 1
        assert view.hidden == 1

    def test_no_overlay_is_fine(self):
        policy, view, _ = _make()
        policy.gamepad_connected_changed(False, overlay=None)
        assert view.hidden == 1
