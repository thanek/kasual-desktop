"""Application controller — wiring between gamepad, desktop, overlay, and tray."""

import logging
import os

from PyQt6.QtCore import QCoreApplication

from desktop import Desktop
from domain.target import AppTarget
from input.gamepad_watcher import GamepadWatcher
from overlays.home_overlay import HomeOverlay, MenuItem
from system.system_actions import ActionDeps
from system.window_manager import KWinWindowManager
from ui import styles
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
        gamepad:     GamepadWatcher,
        desktop:     Desktop,
        action_deps: ActionDeps,
        tray:        SystemTray,
        wm:          KWinWindowManager,
    ) -> None:
        self._gamepad     = gamepad
        self._desktop     = desktop
        self._action_deps = action_deps
        self._tray        = tray
        self._wm          = wm
        self._overlay: HomeOverlay | None = None

        gamepad.btn_mode_pressed.connect(self._on_btn_mode)
        gamepad.connected_changed.connect(self._on_connected_changed)

    def start(self) -> None:
        """Starts periodic window list refresh."""
        self._wm.start_periodic_refresh(3000)

    # ── Event handling ─────────────────────────────────────────────────────

    def _on_btn_mode(self) -> None:
        """BTN_MODE: show the Home Overlay over whatever is on screen.

        The overlay is a layer-shell surface in the `overlay` layer, so it
        floats above the live app/game without minimizing it or touching the
        Desktop. Leaving to the Desktop is handled by _return_to_desktop.
        """
        if self._overlay is not None:
            if self._overlay.isVisible():
                self._overlay.hide_overlay()
                return
            self._overlay.deleteLater()
            self._overlay = None

        running_app = self._desktop.current_app()

        self._overlay = HomeOverlay(
            self._gamepad, self._action_deps, show_confirm=self._desktop.confirm
        )
        self._overlay.closed.connect(self._on_overlay_closed)

        if running_app is None:
            # "Return to Desktop" is an explicit callback that brings KD to the
            # front (works whether KD is merely behind or minimized to the DE).
            # on_cancel stays None so the B button just closes the overlay
            # without yanking the user back to KD when they dismiss it.
            return_item: MenuItem = {
                "label": "  " + QCoreApplication.translate("Kasual", "Return to Desktop"),
                "icon": "fa5s.home",
                "callback": self._desktop.show_desktop,
            }
            items = [return_item] + HomeOverlay.action_items()
            on_cancel = None
        else:
            title     = running_app.name
            close_cb  = lambda t=running_app: self._desktop.request_close_app(t)
            cancel_cb = lambda t=running_app: self._desktop.restore_app(t)

            label = styles.truncate(title, 22)
            items: list[MenuItem] = [
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to {0}").format(label),  "icon": "fa5s.times",        "callback": cancel_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Close {0}").format(label),      "icon": "fa5s.times-circle", "callback": close_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to Desktop"),            "icon": "fa5s.home",         "callback": self._return_to_desktop},
            ]
            on_cancel = cancel_cb
        self._overlay.show_overlay(items=items, on_cancel=on_cancel)

    def _return_to_desktop(self) -> None:
        """Leave the running app and surface the Desktop.

        Phase 1 safety net: the Desktop is a `top`-layer surface, which is not
        guaranteed to stack above an exclusive-fullscreen game, so we still
        minimize the foreground app and raise ourselves via KWin. To be
        revisited in Phase 2 once the Desktop's show/hide model lands.
        """
        running_app = self._desktop.current_app()
        if isinstance(running_app, AppTarget):
            pid = self._desktop.app_manager.running_pid(running_app.index)
            if pid is not None:
                self._wm.minimize_windows_for_pids({pid})
        self._wm.raise_windows_for_pid_exact(os.getpid())
        self._desktop.show_desktop()

    def _on_connected_changed(self, connected: bool) -> None:
        """Gamepad connected / disconnected: synchronizes all components."""
        self._tray.set_connected(connected)
        if connected:
            self._desktop.resume()
        else:
            if self._overlay is not None:
                self._overlay.hide_overlay()
            self._desktop.hide()

    def _on_overlay_closed(self) -> None:
        """Drop the overlay reference once it's dismissed."""
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
