"""The Home Overlay port the controller drives — and its factory.

`SectionedHomeOverlay` is the presentation surface the controller shows on
BTN_MODE: a sectioned overlay (§7.10) that owns its own composition. It extends
`Dismissable` (hide-if-shown) with the rest of its lifecycle so the controller
never touches Qt (`isVisible`/`deleteLater`/the `closed` signal).

`SectionedOverlayFactory` lets the controller create a fresh overlay per press
without knowing the concrete widget or how it is wired to the gamepad.
"""

from collections.abc import Callable
from typing import Protocol

from domain.catalog.target import Target
from domain.navigation.hints import Hints
from domain.shared.event_emitter import Unsubscribe
from domain.menu.item import MenuItem
from domain.shell.session_collaborators import Dismissable
from domain.system.hud import HudControl


class SectionedHomeOverlay(Dismissable, Protocol):
    """The Home Overlay (§7.10) as the controller drives it.

    The widget owns its own composition (it has the volume/brightness controls and
    the power menu), so the controller hands it only the *context* — what is
    foreground — plus the dispatch/cancel callbacks and a hint-pushing callback for
    its zoned hint bar. Quick-adjust sliders and the Power split-button are handled
    inside the widget; everything else is reported back through ``on_action``."""

    def show_for_context(
        self,
        foreground: Target | None,
        foreground_is_game: bool,
        hud: HudControl,
        on_action: Callable[[MenuItem], None],
        on_cancel: Callable[[], None] | None,
        set_hints: Callable[[Hints], None],
        desktop_minimized: bool = False,
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


class SectionedOverlayFactory(Protocol):
    """Creates Home Overlay surfaces on demand (one per BTN_MODE press)."""

    def create_home_overlay(self) -> SectionedHomeOverlay: ...
