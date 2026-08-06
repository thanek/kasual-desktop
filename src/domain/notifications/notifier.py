"""The outbound counterpart of `NotificationSource`: a port for *posting* a
system notification, not observing one."""

from typing import Protocol


class DesktopNotifier(Protocol):
    """Shows a notification through whatever the desktop uses for them."""

    def notify(self, summary: str, body: str = "") -> None: ...
