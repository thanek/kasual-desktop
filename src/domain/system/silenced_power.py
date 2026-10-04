"""Power actions preceded by silencing audio cues — an open stream can fail a suspend."""

from collections.abc import Callable

from domain.shared.feedback import Feedback
from domain.shared.scheduler import Scheduler
from domain.system.power_control import PowerControl

_LETS_THE_AUDIO_SERVER_CLOSE_STREAMS_MS = 300


class SilencedPowerControl(PowerControl):

    def __init__(self, power: PowerControl, feedback: Feedback, scheduler: Scheduler) -> None:
        self._power     = power
        self._feedback  = feedback
        self._scheduler = scheduler

    def suspend(self) -> None:
        self._after_silencing(self._power.suspend)

    def reboot(self) -> None:
        self._after_silencing(self._power.reboot)

    def poweroff(self) -> None:
        self._after_silencing(self._power.poweroff)

    def _after_silencing(self, power_action: Callable[[], None]) -> None:
        self._feedback.silence()
        self._scheduler.call_later(_LETS_THE_AUDIO_SERVER_CLOSE_STREAMS_MS, power_action)
