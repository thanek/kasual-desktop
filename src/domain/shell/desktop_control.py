"""The Desktop operations the BTN_MODE controller (Application) drives."""

from collections.abc import Callable
from typing import Protocol

from domain.catalog.target import Target
from domain.shell.session_collaborators import SessionView


class DesktopControl(SessionView, Protocol):
    """What the `Application` controller drives on the Desktop: query the
    foreground, restore/close the current app, surface the Desktop, raise a
    confirmation, and resolve the foreground app's pid. Inherits resume()/hide()
    from SessionView so the same object also feeds the SessionPolicy."""

    def current_app(self) -> Target | None: ...
    def restore_app(self, target: Target) -> None: ...
    def request_close_app(self, target: Target) -> None: ...
    def show_desktop(self) -> None: ...
    def confirm(self, question: str, on_confirmed: Callable[[], None]) -> None: ...
    def foreground_pid(self) -> int | None: ...
