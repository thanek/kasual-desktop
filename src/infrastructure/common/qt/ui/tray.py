"""System tray icon with context menu."""

from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

from domain.shell.session_collaborators import ConnectionIndicator
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles


class SystemTray(ConnectionIndicator):
    """Encapsulates QSystemTrayIcon, context menu, and icon logic."""

    def __init__(
        self,
        on_show:  Callable[[], None],
        on_logs:  Callable[[], None],
        on_about: Callable[[], None],
        on_quit:  Callable[[], None],
    ) -> None:
        # Held as attributes: a Qt connection keeps only a weak ref to a bound
        # method's object, so a bound-method callback (e.g. log_viewer.open) would
        # die when its owner is GC'd — the menu item then silently does nothing.
        self._on_show  = on_show
        self._on_logs  = on_logs
        self._on_about = on_about
        self._on_quit  = on_quit

        self._tray = QSystemTrayIcon(self._make_icon(connected=False))
        self._tray.setToolTip("Kasual Desktop")

        menu = QMenu()
        show_action = menu.addAction(translate("Kasual Desktop", "Show Desktop"))
        show_action.triggered.connect(self._on_show)
        logs_action = menu.addAction(translate("Kasual Desktop", "Logs"))
        logs_action.triggered.connect(self._on_logs)
        about_action = menu.addAction(translate("Kasual Desktop", "About…"))
        about_action.triggered.connect(self._on_about)
        menu.addSeparator()
        quit_action = menu.addAction(translate("Kasual Desktop", "Quit"))
        quit_action.triggered.connect(self._on_quit)

        # QSystemTrayIcon does not take ownership of the menu, so keep a reference.
        self._menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: on_show()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self._tray.show()

    @staticmethod
    def _make_icon(connected: bool) -> QIcon:
        color = styles.COLOR_ACCENT if connected else "#555555"
        return qta.icon("fa5s.gamepad", color=color)

    def set_connected(self, connected: bool) -> None:
        """Updates the icon based on the gamepad connection state."""
        self._tray.setIcon(self._make_icon(connected))
