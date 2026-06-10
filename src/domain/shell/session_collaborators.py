"""The collaborators SessionPolicy drives as the controller connects/disconnects.

Desktop visibility (the Desktop), the connection surface (the system tray) and
anything dismissable on disconnect (the Home Overlay).
"""

from typing import Protocol


class SessionView(Protocol):
    """Desktop visibility as the session policy drives it (the Desktop)."""

    def resume(self) -> None: ...
    def hide(self) -> None: ...


class ConnectionIndicator(Protocol):
    """Surface reflecting controller-connection state (the system tray)."""

    def set_connected(self, connected: bool) -> None: ...


class Dismissable(Protocol):
    """Something that can be dismissed if currently shown (the Home Overlay)."""

    def hide_overlay(self) -> None: ...
