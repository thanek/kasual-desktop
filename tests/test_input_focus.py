"""Tests for InputFocusStack — the LIFO navigation-event handler stack.

Pure logic, no Qt/evdev. Mirrors (and supersedes) the stack characterization
that previously lived against GamepadWatcher internals in test_gamepad_watcher.
"""

from domain.input.focus_stack import InputFocusStack


class TestSuppress:
    def test_empty_stack_not_suppressed(self):
        assert InputFocusStack().suppressed is False

    def test_push_sets_suppressed(self):
        s = InputFocusStack()
        s.push(lambda e: None)
        assert s.suppressed is True

    def test_pop_clears_suppress_when_empty(self):
        s = InputFocusStack()
        h = lambda e: None
        s.push(h)
        s.pop(h)
        assert s.suppressed is False

    def test_pop_keeps_suppress_when_handlers_remain(self):
        s = InputFocusStack()
        h1, h2 = (lambda e: None), (lambda e: None)
        s.push(h1)
        s.push(h2)
        s.pop(h2)
        assert s.suppressed is True


class TestOrdering:
    def test_top_is_last_pushed(self):
        s = InputFocusStack()
        h1, h2 = (lambda e: None), (lambda e: None)
        s.push(h1)
        s.push(h2)
        assert s.top() is h2

    def test_push_deduplicates_and_moves_to_top(self):
        s = InputFocusStack()
        h1, h2 = (lambda e: None), (lambda e: None)
        s.push(h1)
        s.push(h2)
        s.push(h1)   # already present → moved to top, not duplicated
        assert s.top() is h1
        assert s._handlers == [h2, h1]

    def test_top_none_when_empty(self):
        assert InputFocusStack().top() is None

    def test_pop_nonexistent_is_noop(self):
        InputFocusStack().pop(lambda e: None)   # must not raise

    def test_push_pop_cycle_returns_to_empty(self):
        s = InputFocusStack()
        h = lambda e: None
        for _ in range(5):
            s.push(h)
            s.pop(h)
        assert s.top() is None
        assert s.suppressed is False


class TestDispatch:
    def test_calls_top_handler(self):
        s = InputFocusStack()
        received = []
        s.push(lambda e: received.append(e))
        s.dispatch("select")
        assert received == ["select"]

    def test_calls_only_top_handler(self):
        s = InputFocusStack()
        bottom, top = [], []
        s.push(lambda e: bottom.append(e))
        s.push(lambda e: top.append(e))
        s.dispatch("up")
        assert top == ["up"]
        assert bottom == []

    def test_noop_when_empty(self):
        InputFocusStack().dispatch("down")   # must not raise
