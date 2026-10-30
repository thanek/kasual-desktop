"""System tray icon with context menu."""

from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QActionGroup, QGuiApplication, QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

from domain.display.choices import ScreenChoice, screen_choices
from domain.display.selection import DisplaySelection
from domain.shell.session_collaborators import ConnectionIndicator
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles

TrayIconFor = Callable[[bool], QIcon]

_THEME_ICON = "input-gaming"


def glyph_icon(connected: bool) -> QIcon:
    """The Font Awesome gamepad, tinted by connection state."""
    return qta.icon(
        "fa5s.gamepad", color=styles.COLOR_ACCENT if connected else "#555555",
    )


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
        displays: DisplaySelection,
        icon_for: TrayIconFor = glyph_icon,
    ) -> None:
        # Held as attributes: a Qt connection keeps only a weak ref to a bound
        # method's object, so a bound-method callback (e.g. log_viewer.open) would
        # die when its owner is GC'd — the menu item then silently does nothing.
        self._on_show  = on_show
        self._on_logs  = on_logs
        self._on_about = on_about
        self._on_quit  = on_quit
        self._displays = displays

        self._icon_for = icon_for
        self._tray = QSystemTrayIcon(icon_for(False))
        self._update_tooltip(connected=False)

        menu = QMenu()
        show_action = menu.addAction(translate("Kasual Desktop", "Show Desktop"))
        show_action.triggered.connect(self._on_show)
        self._screens = menu.addMenu(translate("Kasual Desktop", "Screen"))
        self._screen_choices = QActionGroup(self._screens)
        self._list_screens()
        QGuiApplication.instance().screenAdded.connect(self._list_screens)
        QGuiApplication.instance().screenRemoved.connect(self._list_screens)
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

    def _list_screens(self, *_screen_change) -> None:
        self._screens.clear()
        leave_it_to_the_system, *screens = screen_choices(self._displays)
        self._add_screen_choice(leave_it_to_the_system)
        self._screens.addSeparator()
        for choice in screens:
            self._add_screen_choice(choice)

    def _add_screen_choice(self, choice: ScreenChoice) -> None:
        action = self._screens.addAction(choice.label)
        action.setCheckable(True)
        action.setChecked(choice.chosen)
        action.setEnabled(choice.pickable)
        self._screen_choices.addAction(action)
        action.triggered.connect(
            lambda _checked, display_id=choice.display_id: self._choose_screen(display_id))

    def _choose_screen(self, display_id: str | None) -> None:
        self._displays.choose(display_id)
        QTimer.singleShot(0, self._list_screens)

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
