"""The notification-source port the NotificationCenter records from.

Framework-agnostic pub/sub (a single typed subscribe method returning an
``Unsubscribe`` token), mirroring the other domain ports (gamepad, windows,
processes). The implementation (a KDE D-Bus monitor) is responsible for
delivering events on the GUI thread; this port says nothing about threading.
"""

from collections.abc import Callable
from typing import Protocol

from domain.shared.event_emitter import Unsubscribe
from domain.notifications.notification import Notification


class NotificationSource(Protocol):
    """Push source of system notifications as they arrive (KdeNotificationMonitor)."""

    def on_notification(
        self, handler: Callable[[Notification], None]
    ) -> Unsubscribe: ...
