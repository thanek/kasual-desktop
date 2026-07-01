"""The Desktop-surface operations the BTN_MODE controller (Application) drives."""

from collections.abc import Callable
from typing import Protocol

from domain.navigation.hints import Hints
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
    def is_visible(self) -> bool:
        """Whether the Desktop surface is on screen (vs. minimized to tray). Lets
        the controller tell the Home Overlay which foreground-less context it is
        in (Home screen shown vs. Kasual minimized)."""
        ...
    def try_toggle_home_surface(self) -> bool:
        """Context 1 (Home view, `UX.md` §8 / Faza 5): when the persistent Home
        surface is enabled *and* the Desktop is on screen, BTN_MODE expands or
        collapses that surface in place instead of mapping a fresh overlay.
        Returns ``True`` when it handled the press; ``False`` (the default, and
        whenever the surface is off or the Desktop is minimized / an app is
        foreground) leaves the controller to drive the map-on-demand overlay."""
        ...
    def dismiss_overlays(self) -> None: ...
    def begin_overlay_hints(self) -> None: ...
    def end_overlay_hints(self) -> None: ...
    def set_overlay_hints(self, hints: Hints) -> None:
        """Swap the hint bar to *hints* while the overlay is up."""
        ...
    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None: ...
