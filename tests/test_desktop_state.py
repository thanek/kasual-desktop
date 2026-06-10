"""Tests for DesktopState — visibility / paused / foreground transitions (pure)."""

from domain.shell.desktop_state import DesktopState
from domain.shell.foreground import ForegroundState
from domain.catalog.target import AppTarget


class TestInitial:
    def test_starts_hidden_idle_unpaused(self):
        s = DesktopState()
        assert s.visible is False
        assert s.paused is False
        assert s.is_idle() is True


class TestPauseResume:
    def test_pause_hides_and_marks_paused(self):
        s = DesktopState()
        s.go_to_desktop()
        s.pause()
        assert s.visible is False
        assert s.paused is True

    def test_resume_after_pause_restores_overlays(self):
        s = DesktopState()
        s.pause()
        assert s.resume() is True       # was paused → restore overlays
        assert s.visible is True
        assert s.paused is False

    def test_resume_without_pause_does_not_restore(self):
        s = DesktopState()
        assert s.resume() is False      # was not paused


class TestGoToDesktop:
    def test_clears_foreground_and_shows(self):
        fg = ForegroundState()
        fg.set(AppTarget(0, "Steam"))
        s = DesktopState(fg)
        assert s.is_idle() is False
        s.go_to_desktop()
        assert s.is_idle() is True
        assert s.visible is True

    def test_returns_restore_flag_when_was_paused(self):
        s = DesktopState()
        s.pause()
        assert s.go_to_desktop() is True
        assert s.paused is False


class TestSharedForeground:
    def test_composes_the_injected_foreground(self):
        fg = ForegroundState()
        s = DesktopState(fg)
        fg.set(AppTarget(2, "X"))
        assert s.current == AppTarget(2, "X")   # same instance, one truth
