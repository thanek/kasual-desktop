"""Ikona systemowa w zasobniku z menu kontekstowym."""

from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def _make_icon(connected: bool) -> QIcon:
    color = "#88c0d0" if connected else "#555555"
    return qta.icon("fa5s.gamepad", color=color)


class SystemTray:
    """Hermetyzuje QSystemTrayIcon, menu kontekstowe i logikę ikony."""

    def __init__(
        self,
        on_show:  Callable[[], None],
        on_logs:  Callable[[], None],
        on_quit:  Callable[[], None],
    ) -> None:
        self._tray = QSystemTrayIcon(_make_icon(connected=False))
        self._tray.setToolTip("Kasual")

        menu = QMenu()
        show_action = menu.addAction("Pokaż pulpit")
        show_action.triggered.connect(on_show)
        logs_action = menu.addAction("Logi")
        logs_action.triggered.connect(on_logs)
        menu.addSeparator()
        quit_action = menu.addAction("Zamknij")
        quit_action.triggered.connect(on_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: on_show()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self._tray.show()

    def set_connected(self, connected: bool) -> None:
        """Aktualizuje ikonę w zależności od stanu połączenia pada."""
        self._tray.setIcon(_make_icon(connected))
