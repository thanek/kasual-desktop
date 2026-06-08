"""Application controller — wiring between gamepad, desktop, overlay, and tray."""

import logging
import os

from PyQt6.QtCore import QCoreApplication

from application.home_menu import (
    CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP, MenuEntry, compose_home_menu,
)
from application.session import SessionPolicy
from desktop import Desktop
from domain.target import AppTarget, Target
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
        self._session     = SessionPolicy(view=desktop, indicator=tray)

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
        menu = compose_home_menu(running_app)

        self._overlay = HomeOverlay(
            self._gamepad, self._action_deps, show_confirm=self._desktop.confirm
        )
        self._overlay.closed.connect(self._on_overlay_closed)

        items = [self._render_entry(entry, running_app) for entry in menu.entries]
        if menu.include_system_actions:
            items += HomeOverlay.action_items()
        # cancel (B button) returns to the running app when one is foreground;
        # on the bare Desktop it just closes the overlay (None).
        on_cancel = (
            (lambda t=running_app: self._desktop.restore_app(t))
            if menu.cancel_restores_app else None
        )
        self._overlay.show_overlay(items=items, on_cancel=on_cancel)

    def _render_entry(self, entry: MenuEntry, running_app: Target | None) -> MenuItem:
        """Map an abstract menu entry (composed by application.home_menu) to a
        concrete, localized HomeOverlay item with its icon and callback."""
        if entry.kind == RETURN_TO_APP:
            label = styles.truncate(entry.name, 22)
            return {
                "label": "  " + QCoreApplication.translate("Kasual", "Return to {0}").format(label),
                "icon": "fa5s.times",
                "callback": lambda t=running_app: self._desktop.restore_app(t),
            }
        if entry.kind == CLOSE_APP:
            label = styles.truncate(entry.name, 22)
            return {
                "label": "  " + QCoreApplication.translate("Kasual", "Close {0}").format(label),
                "icon": "fa5s.times-circle",
                "callback": lambda t=running_app: self._desktop.request_close_app(t),
            }
        # RETURN_TO_DESKTOP: from a running app we leave it (minimize + raise KD);
        # on the bare Desktop we just bring KD to the front.
        callback = self._return_to_desktop if running_app is not None else self._desktop.show_desktop
        return {
            "label": "  " + QCoreApplication.translate("Kasual", "Return to Desktop"),
            "icon": "fa5s.home",
            "callback": callback,
        }

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
        """Gamepad connected / disconnected: delegate to the session policy."""
        self._session.gamepad_connected_changed(connected, self._overlay)

    def _on_overlay_closed(self) -> None:
        """Drop the overlay reference once it's dismissed."""
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
