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
    """Holds the most recent notifications, newest first.

    Also tracks how many of those are *unread* — notifications that have arrived
    since the user last viewed the list. Because every new notification is added
    at the front and reading clears the tally, the unread ones are always the
    first ``unread_count`` items of :meth:`recent`."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self._items: deque[Notification] = deque(maxlen=limit)
        self._unread = 0

    def record(self, notification: Notification) -> None:
        """Remember a freshly delivered notification (drops the oldest past the
        limit). Newest is kept at the front and counts as unread."""
        self._items.appendleft(notification)
        # Never count more unread than we retain (the oldest fall off the end).
        self._unread = min(self._unread + 1, len(self._items))

    def recent(self, limit: int | None = None) -> list[Notification]:
        """The retained notifications, newest first (optionally capped further)."""
        items = list(self._items)
        return items[:limit] if limit is not None else items

    def mark_all_read(self) -> None:
        """Clear the unread tally — call when the user has seen the list."""
        self._unread = 0

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def unread_count(self) -> int:
        """How many of the retained notifications are still unread."""
        return self._unread
