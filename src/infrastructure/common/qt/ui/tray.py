"""System tray icon with context menu."""

from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

from domain.shell.session_collaborators import ConnectionIndicator
from domain.shared.i18n import translate

TrayIconFor = Callable[[bool], QIcon]

_THEME_ICON = "input-gaming"


def glyph_icon(connected: bool) -> QIcon:
    """The Font Awesome gamepad, tinted by connection state."""
    return qta.icon("fa5s.gamepad", color="#88c0d0" if connected else "#555555")


def themed_icon(connected: bool) -> QIcon:
    """A named icon from the desktop's own theme.

    Some tray hosts render only the ``IconName`` a StatusNotifierItem publishes and
    ignore the serialised pixmap — COSMIC's status area is one, and a glyph icon is
    invisible there because a rasterised font glyph carries no theme name. A theme
    name cannot carry the connection state, so that is left to the tooltip; where
    the theme has no such icon, the glyph is still better than nothing.
    """
    return QIcon.fromTheme(_THEME_ICON, glyph_icon(connected))


class SystemTray(ConnectionIndicator):
    """Encapsulates QSystemTrayIcon, context menu, and icon logic."""

    def __init__(
        self,
        on_show:  Callable[[], None],
        on_logs:  Callable[[], None],
        on_about: Callable[[], None],
        on_quit:  Callable[[], None],
        icon_for: TrayIconFor = glyph_icon,
    ) -> None:
        # Held as attributes: a Qt connection keeps only a weak ref to a bound
        # method's object, so a bound-method callback (e.g. log_viewer.open) would
        # die when its owner is GC'd — the menu item then silently does nothing.
        self._on_show  = on_show
        self._on_logs  = on_logs
        self._on_about = on_about
        self._on_quit  = on_quit

        self._icon_for = icon_for
        self._tray = QSystemTrayIcon(icon_for(False))
        self._update_tooltip(connected=False)

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

    def set_connected(self, connected: bool) -> None:
        """Updates the icon based on the gamepad connection state."""
        self._tray.setIcon(self._icon_for(connected))
        self._update_tooltip(connected)

    def _update_tooltip(self, connected: bool) -> None:
        """Names the connection state in words, the only place it shows where the
        icon cannot carry a colour."""
        state = (translate("Kasual Desktop", "gamepad connected") if connected
                 else translate("Kasual Desktop", "no gamepad"))
        self._tray.setToolTip(f"Kasual Desktop — {state}")
