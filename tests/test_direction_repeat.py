"""Tests for DirectionRepeat — the held-direction auto-fire timing policy.

The clock is a manually advanced fake so the initial delay and repeat interval
are exercised deterministically, with no real sleeping.
"""

from domain.input.direction_repeat import DirectionRepeat
from domain.input.vocabulary import Event


class FakeClock:
    """Manually advanced monotonic clock."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _make(initial_delay=0.4, interval=0.12):
    clock = FakeClock()
    repeat = DirectionRepeat(
        initial_delay=initial_delay, interval=interval, now=clock
    )
    return repeat, clock


class TestNothingHeld:
    def test_due_is_none_when_idle(self):
        repeat, _ = _make()
        assert repeat.due() is None

    def test_timeout_is_default_when_idle(self):
        repeat, _ = _make()
        assert repeat.next_timeout(0.25) == 0.25


class TestInitialDelay:
    def test_no_repeat_before_initial_delay(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.RIGHT)
        clock.advance(0.39)
        assert repeat.due() is None

    def test_repeat_fires_after_initial_delay(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.RIGHT)
        clock.advance(0.4)
        assert repeat.due() == Event.RIGHT


class TestSteadyInterval:
    def test_repeats_at_interval_after_first(self):
        repeat, clock = _make(initial_delay=0.4, interval=0.12)
        repeat.press(Event.DOWN)
        clock.advance(0.4)
        assert repeat.due() == Event.DOWN          # first repeat
        assert repeat.due() is None                # not yet due again
        clock.advance(0.12)
        assert repeat.due() == Event.DOWN          # second repeat

    def test_due_schedules_from_now_not_drift(self):
        """A late poll does not queue up a burst of catch-up repeats."""
        repeat, clock = _make(initial_delay=0.4, interval=0.12)
        repeat.press(Event.UP)
        clock.advance(1.0)                         # long past several intervals
        assert repeat.due() == Event.UP            # one repeat, not a backlog
        assert repeat.due() is None


class TestRelease:
    def test_release_active_stops_repeat(self):
        repeat, clock = _make()
        repeat.press(Event.LEFT)
        repeat.release(Event.LEFT)
        clock.advance(1.0)
        assert repeat.due() is None

    def test_release_other_direction_keeps_repeat(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.LEFT)
        repeat.release(Event.RIGHT)               # a different direction
        clock.advance(0.4)
        assert repeat.due() == Event.LEFT

    def test_clear_stops_repeat(self):
        repeat, clock = _make()
        repeat.press(Event.UP)
        repeat.clear()
        clock.advance(1.0)
        assert repeat.due() is None


class TestTakeover:
    def test_new_direction_replaces_and_restarts_delay(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.LEFT)
        clock.advance(0.3)
        repeat.press(Event.RIGHT)                  # take over before LEFT repeated
        clock.advance(0.3)                         # 0.6 total, but only 0.3 for RIGHT
        assert repeat.due() is None                # RIGHT's delay not elapsed yet
        clock.advance(0.1)
        assert repeat.due() == Event.RIGHT


class TestNextTimeout:
    def test_timeout_tracks_time_until_due(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.RIGHT)
        assert repeat.next_timeout(0.25) == 0.25   # clamped to default
        clock.advance(0.2)
        assert abs(repeat.next_timeout(0.25) - 0.2) < 1e-9

    def test_timeout_never_negative(self):
        repeat, clock = _make(initial_delay=0.4)
        repeat.press(Event.RIGHT)
        clock.advance(1.0)                         # well past due
        assert repeat.next_timeout(0.25) == 0.0
