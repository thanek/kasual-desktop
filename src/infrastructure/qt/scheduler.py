"""Qt adapter for the `Scheduler` port — single-shot deferrals via QTimer."""

from collections.abc import Callable

from PyQt6.QtCore import QTimer

from ports import Scheduler


class QtScheduler(Scheduler):
    """Implements `ports.Scheduler` using Qt's single-shot timer."""

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None:
        QTimer.singleShot(delay_ms, callback)
