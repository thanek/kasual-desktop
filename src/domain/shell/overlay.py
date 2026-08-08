"""The Home Overlay port the controller drives on BTN_MODE — and its factory."""

from collections.abc import Callable
from typing import Protocol

from domain.catalog.target import Target
from domain.navigation.hints import Hints
from domain.shared.event_emitter import Unsubscribe
from domain.menu.item import MenuItem
from domain.shell.session_collaborators import Dismissable
from domain.system.hud import HudControl


class SectionedHomeOverlay(Dismissable, Protocol):
    """The Home Overlay as the controller drives it. The widget owns its own
    composition, so the controller hands it only the context plus callbacks;
    everything the widget doesn't handle is reported back through ``on_action``."""

    def show_for_context(
        self,
        foreground: Target | None,
        foreground_is_game: bool,
        hud: HudControl,
        on_action: Callable[[MenuItem], None],
        on_cancel: Callable[[], None] | None,
        set_hints: Callable[[Hints], None],
        desktop_minimized: bool = False,
        foreground_pid: int | None = None,
    ) -> None:
        """``desktop_minimized`` distinguishes the two foreground-less contexts so
        the overlay can pre-focus the right card: on the bare Home screen it
        highlights "Return to Home screen", but when Kasual is minimized it
        highlights "Minimize" instead (over a running app it always pre-focuses
        "Return to {app}")."""
        ...

    def is_showing(self) -> bool: ...
    def on_closed(self, handler: Callable[[], None]) -> Unsubscribe: ...
    def dispose(self) -> None: ...

    def refresh_hints(self) -> None:
        """Re-push the overlay's own hint set for its current zone."""
        ...

    def request_close(self) -> None:
        """A user dismiss (BTN_MODE while shown): close through the overlay's own
        cancel so it plays the close cue and returns to the app, like B does —
        unlike ``hide_overlay``, the silent mechanical hide used on disconnect."""
        ...


class SectionedOverlayFactory(Protocol):
    """Creates Home Overlay surfaces on demand (one per BTN_MODE press)."""

    def create_home_overlay(self) -> SectionedHomeOverlay: ...
