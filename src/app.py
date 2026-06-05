"""Application controller — wiring between gamepad, desktop, overlay, and tray."""

import logging
import os

from PyQt6.QtCore import QCoreApplication

from desktop import Desktop
from input.gamepad_watcher import GamepadWatcher
from overlays.home_overlay import HomeOverlay, MenuItem
from system.screen_capture import capture_screen
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
        """BTN_MODE: shows overlay with menu adapted to the current context.

        Overlay is always parented to Desktop so it renders inside Desktop's
        Wayland surface — this keeps KDE Plasma panels from bleeding through
        a translucent top-level utility window. When an app is running or
        Desktop is paused, Desktop is first brought to the foreground.
        """
        if self._overlay is not None:
            if self._overlay.isVisible():
                return
            self._overlay.deleteLater()
            self._overlay = None

        # Grab a still of the live screen *before* we minimize the running app
        # and raise the Desktop — the overlay paints it as its background so the
        # user sees whatever they were looking at (game, app, or desktop).
        background = capture_screen()

        running_app = self._desktop.current_app()
        if running_app is not None or not self._desktop.isVisible():
            if not self._desktop.isVisible():
                self._desktop.showFullScreen()

            # Minimize the foreground app — KWin then auto-promotes Desktop
            # to the top with no window-activation animation. raise alone
            # is unreliable when the app holds the topmost slot (e.g. after
            # entering a folder in Pliki the surface becomes fullscreen and
            # KWin refuses to stack anything above it).
            if running_app is not None and running_app['type'] == 'app':
                pid = self._desktop.app_manager.running_pid(running_app['id'])
                if pid is not None:
                    self._wm.minimize_windows_for_pids({pid})

            # Fallback for 'dyn' windows / pause resume: raise our window.
            self._wm.raise_windows_for_pid_exact(os.getpid())

        self._overlay = HomeOverlay(self._gamepad, self._action_deps, parent=self._desktop)
        self._overlay.closed.connect(self._on_overlay_closed)

        if running_app is None:
            items = HomeOverlay.static_items()
            on_cancel = self._desktop.show_desktop
        else:
            title     = running_app['name']
            close_cb  = lambda app=running_app: self._desktop.request_close_app(app)
            cancel_cb = lambda app=running_app: self._desktop.restore_app(app)

            label = styles.truncate(title, 22)
            items: list[MenuItem] = [
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to {0}").format(label),  "icon": "fa5s.times",        "callback": cancel_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Close {0}").format(label),      "icon": "fa5s.times-circle", "callback": close_cb},
                {"label": "  " + QCoreApplication.translate("Kasual", "Return to Desktop"),            "icon": "fa5s.home",         "callback": self._desktop.show_desktop},
            ]
            on_cancel = cancel_cb
        self._overlay.show_overlay(items=items, on_cancel=on_cancel, background=background)

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
