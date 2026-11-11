"""Waiting, off the GUI thread, for sound devices that are still coming back."""

import time
from collections.abc import Callable

from domain.audio.kasual_output import Patience


class PollingPatience(Patience):
    def __init__(self, within_s: float, poll_s: float = 0.25,
                 pause: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.monotonic) -> None:
        self._within_s = within_s
        self._poll_s = poll_s
        self._pause = pause
        self._now = now

    def wait_for(self, ready: Callable[[], bool]) -> None:
        deadline = self._now() + self._within_s
        while not ready() and self._now() < deadline:
            self._pause(self._poll_s)
