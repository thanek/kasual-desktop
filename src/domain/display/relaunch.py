"""A restart the user hears about before Kasual Desktop vanishes from the screen."""

from typing import Protocol

from domain.notifications.notifier import DesktopNotifier
from domain.shared.i18n import translate
from domain.shared.scheduler import Scheduler

_TIME_TO_READ_THE_NOTICE_MS = 3000


class SessionRestart(Protocol):
    def restart(self) -> None: ...


class AnnouncedRelaunch:
    def __init__(
        self, notifier: DesktopNotifier, scheduler: Scheduler, restart: SessionRestart,
    ) -> None:
        self._notifier = notifier
        self._scheduler = scheduler
        self._restart = restart

    def relaunch_onto_another_screen(self) -> None:
        self._notifier.notify(
            translate("Kasual Desktop", "Kasual Desktop will restart"),
            translate("Kasual Desktop",
                      "Moving to another screen needs a restart on this desktop"),
        )
        self._scheduler.call_later(_TIME_TO_READ_THE_NOTICE_MS, self._restart.restart)
