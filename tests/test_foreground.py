"""Tests for ForegroundState — the foreground-target state machine.

Pure domain, no Qt. These lock the transitions that previously lived as bare
assignments in Desktop, including the 'clear when the foreground app
finished / failed to launch' rule behind two earlier bug fixes.
"""

from domain.foreground import ForegroundState
from domain.target import AppTarget, WindowTarget


def _app(i=0):
    return AppTarget(index=i, name=f"App {i}")


def _win(wid="w1"):
    return WindowTarget(window_id=wid, name="Win")


class TestBasics:
    def test_starts_idle(self):
        fg = ForegroundState()
        assert fg.is_idle() is True
        assert fg.current is None

    def test_set_makes_it_current(self):
        fg = ForegroundState()
        t = _app(2)
        fg.set(t)
        assert fg.current is t
        assert fg.is_idle() is False

    def test_clear(self):
        fg = ForegroundState()
        fg.set(_app())
        fg.clear()
        assert fg.is_idle() is True


class TestClearIfApp:
    def test_clears_matching_app(self):
        fg = ForegroundState()
        fg.set(_app(3))
        fg.clear_if_app(3)
        assert fg.is_idle() is True

    def test_keeps_different_app(self):
        fg = ForegroundState()
        fg.set(_app(3))
        fg.clear_if_app(4)        # a different app finished
        assert fg.current == _app(3)

    def test_keeps_window_target(self):
        fg = ForegroundState()
        fg.set(_win())
        fg.clear_if_app(0)        # index must not match a WindowTarget
        assert isinstance(fg.current, WindowTarget)

    def test_noop_when_idle(self):
        fg = ForegroundState()
        fg.clear_if_app(0)        # must not raise
        assert fg.is_idle() is True
