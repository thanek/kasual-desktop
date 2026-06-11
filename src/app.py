"""Application controller — wiring between gamepad, desktop, overlay, and tray."""

import logging
import os

from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.home import compose_home_menu
from domain.menu.item import MenuItem
from domain.lifecycle.window_manager import WindowManager
from domain.shell.desktop_control import DesktopControl
from domain.shell.session import SessionPolicy
from domain.shell.session_collaborators import ConnectionIndicator
from domain.system.actions import ActionDeps
from domain.system.action_view import make_action_confirm
from domain.system.runner import ActionRunner
# Concrete (deferred to a later session): the gamepad signals and the overlay's
# Qt lifecycle still tie Application to these two infrastructure types.
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.overlays.home_overlay import HomeOverlay

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
        desktop:     DesktopControl,
        action_deps: ActionDeps,
        tray:        ConnectionIndicator,
        wm:          WindowManager,
    ) -> None:
        self._gamepad     = gamepad
        self._desktop     = desktop
        self._tray        = tray
        self._wm          = wm
        self._overlay: HomeOverlay | None = None
        self._session     = SessionPolicy(view=desktop, indicator=tray)
        # System actions (sleep/shutdown/…) run through the domain ActionRunner,
        # gating the confirmable ones on the Desktop's tracked confirm dialog.
        self._action_runner = ActionRunner(
            action_deps, make_action_confirm(desktop.confirm)
        )

        gamepad.btn_mode_pressed.connect(self._on_btn_mode)
        gamepad.connected_changed.connect(self._on_connected_changed)

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

        menu = compose_home_menu(self._desktop.current_app())

        self._overlay = HomeOverlay(self._gamepad)
        self._overlay.closed.connect(self._on_overlay_closed)

        # cancel (B button) returns to the running app when one is foreground;
        # on the bare Desktop it just closes the overlay (None).
        on_cancel = (
            (lambda t=menu.cancel_restores: self._desktop.restore_app(t))
            if menu.cancel_restores is not None else None
        )
        self._overlay.show_overlay(
            items=menu.items, on_select=self._dispatch_home, on_cancel=on_cancel
        )

    def _dispatch_home(self, item: MenuItem) -> None:
        """Perform the behaviour for an activated Home Overlay item."""
        if item.action == RETURN_TO_APP:
            self._desktop.restore_app(item.target)
        elif item.action == CLOSE_APP:
            self._desktop.request_close_app(item.target)
        elif item.action == RETURN_TO_DESKTOP:
            # From a running app we leave it (minimize + raise KD); on the bare
            # Desktop we just bring KD to the front.
            if self._desktop.current_app() is not None:
                self._return_to_desktop()
            else:
                self._desktop.show_desktop()
        else:
            # A system-action key (volume, sleep, …).
            self._action_runner.run(item.action)

    def _return_to_desktop(self) -> None:
        """Leave the running app and surface the Desktop.

        Phase 1 safety net: the Desktop is a `top`-layer surface, which is not
        guaranteed to stack above an exclusive-fullscreen game, so we still
        minimize the foreground app and raise ourselves via KWin. To be
        revisited in Phase 2 once the Desktop's show/hide model lands.
        """
        pid = self._desktop.foreground_pid()
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
