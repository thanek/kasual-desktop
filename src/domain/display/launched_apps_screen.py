from domain.display.display import PrimaryDisplay
from domain.lifecycle.app_events import AppFinished, AppStarted
from domain.lifecycle.process_manager import ProcessManager
from domain.shared.scheduler import Scheduler

RELAUNCH_GRACE_MS = 3000


class LaunchedAppsFollowKasual:
    def __init__(
        self, processes: ProcessManager, primary: PrimaryDisplay, scheduler: Scheduler,
    ) -> None:
        self._primary = primary
        self._scheduler = scheduler
        self._running: set[str] = set()
        self._lent = False
        self._launches = 0
        processes.on_started(self._started)
        processes.on_finished(self._finished)

    def release(self) -> None:
        self._running.clear()
        self._launches += 1
        self._reclaim()

    def _started(self, event: AppStarted) -> None:
        self._launches += 1
        self._running.add(event.app_id)
        if not self._lent:
            self._lent = True
            self._primary.lend_to_kasual_screen()

    def _finished(self, event: AppFinished) -> None:
        self._running.discard(event.app_id)
        if self._running:
            return
        launches_so_far = self._launches
        self._scheduler.call_later(
            RELAUNCH_GRACE_MS, lambda: self._reclaim_unless_relaunched(launches_so_far))

    def _reclaim_unless_relaunched(self, launches_then: int) -> None:
        if self._launches == launches_then:
            self._reclaim()

    def _reclaim(self) -> None:
        self._lent = False
        self._primary.reclaim()
