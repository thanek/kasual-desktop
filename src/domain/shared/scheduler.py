"""The delayed-callback port — cross-cutting timer capability."""

from collections.abc import Callable
from typing import Protocol


class Scheduler(Protocol):
    """Run a callback after a delay, without coupling the application layer to a
    concrete timer (Qt's QTimer.singleShot in production)."""

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None: ...
