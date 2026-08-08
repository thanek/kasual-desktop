"""Qt adapter for the `Scheduler` port — single-shot deferrals via QTimer."""

from collections.abc import Callable

from PyQt6.QtCore import QTimer

from domain.shared.scheduler import Scheduler


class QtScheduler(Scheduler):
    """Implements `ports.Scheduler` using Qt's single-shot timer."""

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None:
        def keep_callback_alive_until_it_runs() -> None:
            callback()

        QTimer.singleShot(delay_ms, keep_callback_alive_until_it_runs)
