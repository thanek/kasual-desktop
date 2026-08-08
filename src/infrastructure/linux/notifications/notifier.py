"""freedesktop notification sink — the `Notify` call `notifications.py` watches for.

Blocks: the caller may exit the moment `notify()` returns.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QMetaType
from PyQt6.QtDBus import QDBus, QDBusArgument, QDBusConnection, QDBusMessage

from domain.notifications.notifier import DesktopNotifier

logger = logging.getLogger(__name__)

_SERVICE = "org.freedesktop.Notifications"
_PATH = "/org/freedesktop/Notifications"

_TIMEOUT_MS = 3000

_NO_HINTS: dict = {}
_DAEMON_DEFAULT_EXPIRY = -1


def _as_dbus_uint32(value: int) -> QDBusArgument:
    return QDBusArgument(value, QMetaType.Type.UInt.value)


def _as_dbus_string_list(values: list[str]) -> QDBusArgument:
    return QDBusArgument(values, QMetaType.Type.QStringList.value)


class FreedesktopNotifier(DesktopNotifier):
    def __init__(self, app_name: str = "Kasual Desktop", icon: str = "kasual-desktop") -> None:
        self._app_name = app_name
        self._icon = icon

    def notify(self, summary: str, body: str = "") -> None:
        replaces_nothing = _as_dbus_uint32(0)
        no_actions = _as_dbus_string_list([])

        message = QDBusMessage.createMethodCall(_SERVICE, _PATH, _SERVICE, "Notify")
        message.setArguments([
            self._app_name, replaces_nothing, self._icon, summary, body,
            no_actions, _NO_HINTS, _DAEMON_DEFAULT_EXPIRY,
        ])

        reply = QDBusConnection.sessionBus().call(message, QDBus.CallMode.Block, _TIMEOUT_MS)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            logger.warning(
                "Could not show the notification %r: %s", summary, reply.errorName(),
            )
