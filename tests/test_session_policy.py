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

    def hide(self):
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


def _make():
    view = FakeView()
    indicator = FakeIndicator()
    return SessionPolicy(view, indicator), view, indicator


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
