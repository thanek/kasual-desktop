"""The outbound counterpart of `NotificationSource`: a port for *posting* a
system notification, not observing one."""

from typing import Protocol


class DesktopNotifier(Protocol):
    def notify(self, summary: str, body: str = "") -> None: ...
