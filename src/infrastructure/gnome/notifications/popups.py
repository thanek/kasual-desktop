"""NotificationPopups adapter over the Kasual Helper GNOME Shell extension."""

import logging

from PyQt6.QtDBus import QDBusConnection

from domain.notifications.popups import NotificationPopups
from infrastructure.gnome import helper

logger = logging.getLogger(__name__)

NAME_OWNED_WHILE_A_GAMEPAD_DRIVES = "org.consoledesktop.KasualGamepad"


class GnomeNotificationPopups(NotificationPopups):
    def expire_without_keyboard_or_mouse(self) -> None:
        bus = QDBusConnection.sessionBus()
        if not bus.registerService(NAME_OWNED_WHILE_A_GAMEPAD_DRIVES):
            logger.warning("Cannot own %s: notification banners may stay on screen",
                           NAME_OWNED_WHILE_A_GAMEPAD_DRIVES)

    def wait_for_keyboard_or_mouse(self) -> None:
        QDBusConnection.sessionBus().unregisterService(NAME_OWNED_WHILE_A_GAMEPAD_DRIVES)

    def dismiss_all(self) -> None:
        helper.dismiss_banners()
