"""The Home Overlay ports the controller drives — and its factory.

`HomeMenuOverlay` is the presentation surface the controller shows on BTN_MODE:
it renders a domain-composed menu and reports activation/cancellation back. It
extends `Dismissable` (hide-if-shown) with the rest of its lifecycle so the
controller never touches Qt (`isVisible`/`deleteLater`/the `closed` signal).

`OverlayFactory` lets the controller create a fresh overlay per press without
knowing the concrete widget or how it is wired to the gamepad.
"""

from collections.abc import Callable
from typing import Protocol

from domain.shared.event_emitter import Unsubscribe
from domain.menu.item import MenuItem
from domain.shell.session_collaborators import Dismissable


class HomeMenuOverlay(Dismissable, Protocol):
    """The Home Overlay as the controller drives it (the HomeOverlay widget)."""

    def show_overlay(
        self,
        items: list[MenuItem],
        on_select: Callable[[MenuItem], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None: ...

    def is_showing(self) -> bool: ...
    def on_closed(self, handler: Callable[[], None]) -> Unsubscribe: ...
    def dispose(self) -> None: ...


class OverlayFactory(Protocol):
    """Creates Home Overlays on demand (one per BTN_MODE press)."""

    def create_home_overlay(self) -> HomeMenuOverlay: ...
