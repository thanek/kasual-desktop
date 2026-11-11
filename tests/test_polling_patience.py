"""Tests for PollingPatience."""

from infrastructure.common.audio.patience import PollingPatience


class FakeClock:
    def __init__(self):
        self.time = 0.0

    def now(self):
        return self.time

    def pause(self, seconds):
        self.time += seconds


def _patience(clock, within_s=1.0):
    return PollingPatience(within_s=within_s, poll_s=0.25, pause=clock.pause, now=clock.now)


def test_stops_waiting_as_soon_as_ready():
    clock = FakeClock()
    _patience(clock).wait_for(lambda: clock.time >= 0.5)
    assert clock.time == 0.5


def test_gives_up_after_the_deadline():
    clock = FakeClock()
    _patience(clock).wait_for(lambda: False)
    assert clock.time == 1.0


def test_does_not_wait_for_what_is_already_ready():
    clock = FakeClock()
    _patience(clock).wait_for(lambda: True)
    assert clock.time == 0.0
