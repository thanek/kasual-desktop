"""The app-control port the Application controller drives (AppLifecycle).

Restoring, closing and querying the foreground app are app-lifecycle concerns,
so the controller talks to the lifecycle coordinator directly through this port
rather than routing the calls through the Desktop widget. Consumer-driven (ISP):
exactly the four operations `Application` needs.
"""

from typing import Protocol

from domain.catalog.target import Target


class AppControl(Protocol):
    """Foreground-app control as the Application controller drives it."""

    def current_app(self) -> Target | None: ...
    def restore_app(self, target: Target) -> None: ...
    def request_close_app(self, target: Target) -> None: ...
    def foreground_pid(self) -> int | None: ...
    def foreground_is_game(self) -> bool: ...
