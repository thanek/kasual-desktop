"""Application controller — wiring between gamepad, desktop, overlay, and tray."""

import logging

from PyQt6.QtCore import QCoreApplication

from desktop import Desktop
from input.gamepad_watcher import GamepadWatcher
from overlays.home_overlay import HomeOverlay, MenuItem
from system.window_manager import KWinWindowManager
from ui.tray import SystemTray

logger = logging.getLogger(__name__)


class Application:
    """
    Connects all application components and handles global events:
      - BTN_MODE → builds context menu and shows HomeOverlay
      - connected_changed → synchronizes state of desktop, overlay, and tray
    """

    def __init__(
        self,
        gamepad: GamepadWatcher,
        desktop: Desktop,
        overlay: HomeOverlay,
        tray:    SystemTray,
        wm:      KWinWindowManager,
    ) -> None:
        self._gamepad = gamepad
        self._desktop = desktop
        self._overlay = overlay
        self._tray    = tray
        self._wm      = wm

        gamepad.btn_mode_pressed.connect(self._on_btn_mode)
        gamepad.connected_changed.connect(self._on_connected_changed)

    def start(self) -> None:
        """Starts periodic window list refresh."""
        self._wm.start_periodic_refresh(3000)

    # ── Event handling ─────────────────────────────────────────────────────

    def _on_btn_mode(self) -> None:
        """BTN_MODE: shows overlay with menu adapted to the current context."""
        running_app = self._desktop.current_app()

        if running_app is None:
            items = self._overlay.static_items()
        else:
            title     = running_app['name']
            close_cb  = lambda app=running_app: self._desktop.request_close_app(app)
            cancel_cb = lambda app=running_app: self._desktop.restore_app(app)

            label = title if len(title) <= 22 else title[:21] + '…'
            items: list[MenuItem] = [
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to {0}").format(label),  "icon": "fa5s.times",        "callback": cancel_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Close {0}").format(label),      "icon": "fa5s.times-circle", "callback": close_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to Desktop"),            "icon": "fa5s.home",         "callback": self._desktop.show_desktop},
            ]
        self._overlay.show_overlay(items=items, on_cancel=self._desktop.show_desktop)

    def _on_connected_changed(self, connected: bool) -> None:
        """Gamepad connected / disconnected: synchronizes all components."""
        self._tray.set_connected(connected)
        if connected:
            self._desktop.resume()
        else:
            self._overlay.hide_overlay()
            self._desktop.hide()
