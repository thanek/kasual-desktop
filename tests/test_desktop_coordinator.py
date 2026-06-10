"""Tests for the Desktop coordinator — show/pause/resume orchestration (no Qt).

Characterizes the exact step sequence (and the paused→restore-overlays gating)
that previously lived inline in the Qt widget's show_desktop/pause/resume.
"""

from unittest.mock import MagicMock

from domain.shell.desktop import Desktop
from domain.shell.desktop_state import DesktopState
from domain.shell.foreground import ForegroundState
from domain.catalog.target import AppTarget


class FakeView:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        # Any view step records itself by name (take_input, show_fullscreen, …).
        def step(*_a, **_k):
            self.calls.append(name)
        return step


def _make():
    fg = ForegroundState()
    state = DesktopState(fg)
    view = FakeView()
    feedback = MagicMock()
    return Desktop(state, view, feedback), state, view, feedback


class TestShowDesktop:
    def test_sequence_when_not_paused(self):
        coord, state, view, _ = _make()
        coord.show_desktop()
        assert view.calls == [
            "take_input", "refresh_windows", "show_fullscreen", "activate",
        ]
        assert state.is_idle() is True
        assert state.visible is True

    def test_clears_foreground(self):
        coord, state, _, _ = _make()
        state.foreground.set(AppTarget(0, "Steam"))
        coord.show_desktop()
        assert state.is_idle() is True

    def test_restores_overlays_when_was_paused(self):
        coord, _, view, _ = _make()
        coord.pause()
        view.calls.clear()
        coord.show_desktop()
        assert "resume_overlays" in view.calls


class TestPause:
    def test_sequence(self):
        coord, state, view, feedback = _make()
        coord.pause()
        assert view.calls == ["pause_overlays", "release_input", "hide_view"]
        assert state.paused is True
        assert state.visible is False
        feedback.play.assert_called_once_with("exit")


class TestResume:
    def test_sequence_when_not_paused(self):
        coord, _, view, feedback = _make()
        coord.resume()
        assert view.calls == ["take_input", "show_fullscreen", "activate"]
        feedback.play.assert_called_once_with("start")

    def test_restores_overlays_when_was_paused(self):
        coord, _, view, _ = _make()
        coord.pause()
        view.calls.clear()
        coord.resume()
        assert view.calls == [
            "take_input", "show_fullscreen", "resume_overlays", "activate",
        ]

    def test_resume_keeps_foreground(self):
        coord, state, _, _ = _make()
        state.foreground.set(AppTarget(1, "X"))
        coord.resume()
        assert state.current == AppTarget(1, "X")   # resume does not clear
