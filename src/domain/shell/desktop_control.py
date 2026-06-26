"""The Desktop-surface operations the BTN_MODE controller (Application) drives."""

from collections.abc import Callable
from typing import Protocol

from domain.shell.session_collaborators import SessionView


class DesktopControl(SessionView, Protocol):
    """The Desktop-surface operations the `Application` controller drives: bring
    the Desktop forward, raise a confirmation dialog, and dismiss any open
    overlays (cancelling their action) so a freshly raised Home Overlay
    supersedes rather than covers them. Inherits resume()/hide() from SessionView
    so the same object also feeds the SessionPolicy.

    Foreground-app control (restore / close / query) is *not* here — those are
    app-lifecycle concerns the controller drives on the lifecycle coordinator
    directly, through the `AppControl` port."""

    def show_desktop(self) -> None: ...
    def dismiss_overlays(self) -> None: ...
    def begin_overlay_hints(self) -> None: ...
    def end_overlay_hints(self) -> None: ...
    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None: ...
