"""The notification center: the recent-notifications buffer.

Pure use-case, no Qt/D-Bus. Keeps a bounded history of the most recently arrived
notifications, newest first, so the overlay can render "the last few". The
bound is the one domain rule here — old notifications fall off the end.

It does not subscribe to the source itself: the composition root wires
``source.on_notification(center.record)``, keeping this free of any port wiring
(and trivially unit-testable by calling ``record`` directly).
"""

from collections import deque

from domain.notifications.notification import Notification

DEFAULT_LIMIT = 20   # how many recent notifications to retain


class NotificationCenter:
    """Holds the most recent notifications, newest first."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self._items: deque[Notification] = deque(maxlen=limit)

    def record(self, notification: Notification) -> None:
        """Remember a freshly delivered notification (drops the oldest past the
        limit). Newest is kept at the front."""
        self._items.appendleft(notification)

    def recent(self, limit: int | None = None) -> list[Notification]:
        """The retained notifications, newest first (optionally capped further)."""
        items = list(self._items)
        return items[:limit] if limit is not None else items

    @property
    def count(self) -> int:
        return len(self._items)
