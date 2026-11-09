"""The collaborators SessionPolicy drives as the controller connects/disconnects.

Desktop visibility (the Desktop), the connection surface (the system tray), the
sound output Kasual Desktop borrows while in charge, and anything dismissable on
disconnect (the Home Overlay).
"""

from typing import Protocol


class SessionView(Protocol):
    """Desktop visibility as the session policy drives it (the Desktop)."""

    def resume(self) -> None: ...
    def withdraw(self) -> None:
        """Leave the screen entirely — the Home chrome (header, hint bar) is its
        own surface and must come down with it."""
        ...


class SessionSound(Protocol):
    def take_over(self) -> None: ...
    def give_back(self) -> None: ...


class ConnectionIndicator(Protocol):
    """Surface reflecting controller-connection state (the system tray)."""

    def set_connected(self, connected: bool) -> None: ...


class Dismissable(Protocol):
    """Something that can be dismissed if currently shown (the Home Overlay)."""

    def hide_overlay(self) -> None: ...
