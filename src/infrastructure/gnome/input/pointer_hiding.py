import logging

from PyQt6.QtDBus import QDBusConnection

from domain.input.pointer_hiding import PointerHiding

logger = logging.getLogger(__name__)

NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES = "org.consoledesktop.KasualIdlePointer"


class GnomePointerHiding(PointerHiding):
    def hide_while_idle(self) -> None:
        if not QDBusConnection.sessionBus().registerService(
                NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES):
            logger.warning("Cannot own %s: the idle pointer stays on screen",
                           NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES)

    def keep_visible(self) -> None:
        QDBusConnection.sessionBus().unregisterService(
            NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES)
