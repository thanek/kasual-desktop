"""SessionEnder adapter over ``org.gnome.SessionManager``.

Logout mode 1 skips GNOME's own confirmation screen — the preflight dialog the
user just answered is that confirmation — while still honouring inhibitors, so an
app with unsaved work can still put its dialog in the way. It goes over as an
explicit uint32: PyQt marshals a plain int as int32, which the signature rejects.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QMetaType
from PyQt6.QtDBus import (
    QDBusArgument, QDBusConnection, QDBusInterface, QDBusMessage,
)

from domain.preflight.extension import SessionEnder

logger = logging.getLogger(__name__)

SERVICE = "org.gnome.SessionManager"
OBJECT_PATH = "/org/gnome/SessionManager"

_NO_CONFIRMATION = 1


class GnomeSessionEnder(SessionEnder):
    def log_out(self) -> None:
        iface = QDBusInterface(
            SERVICE, OBJECT_PATH, SERVICE, QDBusConnection.sessionBus())
        mode = QDBusArgument(_NO_CONFIRMATION, QMetaType.Type.UInt.value)
        reply = iface.call("Logout", mode)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            logger.warning("Logout failed: %s", reply.errorMessage())
