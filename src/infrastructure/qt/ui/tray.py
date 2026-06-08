"""System tray icon with context menu."""

from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


class SystemTray:
    """Encapsulates QSystemTrayIcon, context menu, and icon logic."""

    def __init__(
        self,
        on_show:  Callable[[], None],
        on_logs:  Callable[[], None],
        on_quit:  Callable[[], None],
    ) -> None:
        self._tray = QSystemTrayIcon(self._make_icon(connected=False))
        self._tray.setToolTip("Kasual Desktop")

        menu = QMenu()
        show_action = menu.addAction(QCoreApplication.translate("Kasual", "Show Desktop"))
        show_action.triggered.connect(on_show)
        logs_action = menu.addAction(QCoreApplication.translate("Kasual", "Logs"))
        logs_action.triggered.connect(on_logs)
        menu.addSeparator()
        quit_action = menu.addAction(QCoreApplication.translate("Kasual", "Quit"))
        quit_action.triggered.connect(on_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: on_show()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self._tray.show()

    @staticmethod
    def _make_icon(connected: bool) -> QIcon:
        color = "#88c0d0" if connected else "#555555"
        return qta.icon("fa5s.gamepad", color=color)

    def set_connected(self, connected: bool) -> None:
        """Updates the icon based on the gamepad connection state."""
        self._tray.setIcon(self._make_icon(connected))
