import logging
import os
from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher, BTN_MODE_CLICK
from overlays.base_overlay import BaseOverlay
from overlays.confirm_dialog import ConfirmDialog
from overlays.info_dialog import InfoDialog
from overlays.tile_popover import TilePopoverMenu
from overlays.volume_overlay import VolumeOverlay
from system.app_manager import AppManager
from system.system_actions import ActionDeps, ActionRunner
from system.window_manager import KWinWindowManager
from ui import styles
from .tile_bar import TileBar
from .topbar import TopBar
from .wallpaper import KdeWallpaperLoader

logger = logging.getLogger(__name__)


class Desktop(QWidget):
    """Main environment window — always fullscreen."""

    def __init__(
        self,
        apps: list[dict],
        gamepad: GamepadWatcher,
        window_manager: KWinWindowManager,
    ):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._wm          = window_manager
        self._app_manager = AppManager(self)
        self._focus_mode     = "tiles"   # "tiles" | "topbar"
        self._topbar_index   = 0
        self._confirm_dialog = None
        self._volume_overlay = None
        self._tile_popover   = None
        self._is_paused      = False
        # Reference-counted "minimal mode" — when >0, topbar and tile bar are
        # hidden so the only thing showing through an overlay's translucent
        # background is the wallpaper.
        self._overlay_depth  = 0

        # Currently active app/window — what BTN_MODE context menu will target
        # {'type': 'app', 'id': idx, 'name': ...} or {'type': 'dyn', 'id': win_id, 'name': ...}
        # dyn contexts also carry 'trigger' (BTN_MODE_CLICK / BTN_MODE_HOLD_1S)
        self._active_context: dict | None                    = None

        self.setWindowTitle("Kasual Desktop")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self._topbar = TopBar()
        self._topbar.action_triggered.connect(self._topbar_action)
        self._topbar.button_hovered.connect(self._on_topbar_hovered)
        main.addWidget(self._topbar)
        main.addStretch(1)
        self._tilebar = TileBar(self._apps, self._app_manager)
        self._tilebar.activated.connect(self._on_tile_activated)
        self._tilebar.windows_changed.connect(self._check_active_dyn_gone)
        self._tilebar.tile_hovered.connect(self._on_tile_hovered)
        self._tilebar.tile_context_menu.connect(self._on_tile_context_menu)
        main.addWidget(self._tilebar)
        main.addStretch(1)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tilebar.refresh_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = KdeWallpaperLoader().load()

        self._action_runner = ActionRunner(
            ActionDeps(desktop=self),
            lambda q, cb: self._show_confirm(question=q, on_confirmed=cb),
        )

        self._app_manager.app_finished.connect(self._on_app_finished)
        self._app_manager.app_launch_failed.connect(self._on_app_launch_failed)
        self._wm.windows_updated.connect(self._tilebar.update_windows)

        QApplication.instance().installEventFilter(self)

        # Desktop is not shown at startup — we wait for the connected_changed(True) signal

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def app_manager(self) -> AppManager:
        return self._app_manager

    def show_desktop(self) -> None:
        """Show the desktop without interrupting the running application."""
        self._active_context = None
        self._gamepad.push_handler(self._handle_pad)
        self._wm.refresh_now()
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    def enter_overlay_mode(self) -> None:
        """Hide topbar and tile bar so an overlay shows only the wallpaper."""
        self._overlay_depth += 1
        if self._overlay_depth == 1:
            self._topbar.hide()
            self._tilebar.hide()

    def exit_overlay_mode(self) -> None:
        """Restore topbar and tile bar when the last overlay closes."""
        self._overlay_depth = max(0, self._overlay_depth - 1)
        if self._overlay_depth == 0:
            self._topbar.show()
            self._tilebar.show()

    @property
    def _active_overlays(self) -> list[BaseOverlay]:
        """Active overlays (those that can be paused/resumed)."""
        return [o for o in (self._volume_overlay, self._confirm_dialog) if o is not None]

    def pause(self) -> None:
        """Hide the Desktop without disconnecting the gamepad (minimize to tray)."""
        sound_player.play("exit")
        self._is_paused = True
        for overlay in self._active_overlays:
            overlay.pause()
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def resume(self) -> None:
        """Restore the Desktop after reconnecting the gamepad — without resetting state."""
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("start")
        self.showFullScreen()
        self._restore_overlays()
        self.activateWindow()

    def _restore_overlays(self) -> None:
        """Restore overlays hidden by pause(). No-op if we were not paused."""
        if not self._is_paused:
            return
        self._is_paused = False
        for overlay in self._active_overlays:
            overlay.resume()

    def current_app(self) -> dict | None:
        """Returns the currently active app/window context, or None if on desktop."""
        return self._active_context

    def restore_app(self, app) -> None:
        sound_player.play("select")
        if app['type'] == 'app':
            idx = app['id']
            trigger = self._apps[idx].get("recall_menu_trigger", BTN_MODE_CLICK)
            self._gamepad.set_app_btn_mode_trigger(trigger)
            self._arrange_windows(self._app_manager.running_pid(idx))
        else:
            self._gamepad.set_app_btn_mode_trigger(app.get('trigger', BTN_MODE_CLICK))
            self._wm.activate_window(app['id'])
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def request_close_app(self, app) -> None:
        display = styles.truncate(app['name'], 40)

        def _confirmed() -> None:
            self._restore_desktop_view()
            if app['type'] == 'app':
                self._tilebar.set_static_closing(app['id'])
                self._app_manager.terminate(app['id'])
            else:
                self._active_context = None
                self._wm.close_window(app['id'])
                QTimer.singleShot(1000, self._wm.refresh_now)

        self._show_confirm(
            question=self.tr('Are you sure you want to close\n"{0}"?').format(display),
            on_confirmed=_confirmed,
            on_cancelled=self._restore_desktop_view,
        )


    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._tilebar.center_current)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_tilebar'):
            QTimer.singleShot(0, self._tilebar.center_current)

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        if self._wallpaper and not self._wallpaper.isNull():
            scaled = self._wallpaper.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width()  - scaled.width())  // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#0b140e"))

    # ── Tile bar coordination ───────────────────────────────────────────────

    def _check_active_dyn_gone(self) -> None:
        """If the active dynamic window disappeared (closed by the app) → show desktop."""
        ctx = self._active_context
        if ctx is not None and ctx.get('type') == 'dyn':
            if not self._tilebar.has_dynamic_window(ctx['id']):
                self._active_context = None
                if not self.isVisible():
                    self._reactivate_desktop()

    def _render_focus(self) -> None:
        """Repaint the focus highlight across the tile bar and top bar."""
        in_tiles = self._focus_mode == "tiles"
        self._tilebar.set_focused(in_tiles)
        self._topbar.set_selected(self._topbar_index if not in_tiles else None)

    def _focus_moved(self) -> None:
        """Repaint focus highlight and play the cursor-move sound."""
        self._render_focus()
        sound_player.play("cursor")

    # ── Gamepad handler ────────────────────────────────────────────────────

    _KEY_MAP = {
        Qt.Key.Key_Left:   "left",
        Qt.Key.Key_Right:  "right",
        Qt.Key.Key_Up:     "up",
        Qt.Key.Key_Down:   "down",
        Qt.Key.Key_Return: "select",
        Qt.Key.Key_Enter:  "select",
        Qt.Key.Key_Escape: "cancel",
        Qt.Key.Key_Q:      "close",
    }

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        mapped = self._KEY_MAP.get(event.key())
        if mapped:
            self._gamepad.inject(mapped)
            return True
        return False

    def _handle_pad(self, event: str) -> None:
        if self._focus_mode == "tiles":
            if event == "left":
                if self._tilebar.move(-1):
                    sound_player.play("cursor")
            elif event == "right":
                if self._tilebar.move(+1):
                    sound_player.play("cursor")
            elif event == "up" and self._topbar.count:
                self._focus_mode = "topbar"
                self._topbar_index = 0
                self._focus_moved()
            elif event == "select":
                self._tilebar.select_current()
            elif event == "close":
                self._show_tile_popover()

        elif self._focus_mode == "topbar":
            if event == "left":
                self._topbar_index = (self._topbar_index - 1) % self._topbar.count
                self._focus_moved()
            elif event == "right":
                self._topbar_index = (self._topbar_index + 1) % self._topbar.count
                self._focus_moved()
            elif event in ("down", "cancel"):
                self._focus_mode = "tiles"
                self._focus_moved()
            elif event == "select":
                self._topbar.trigger(self._topbar_index)

    # ── Tile actions ───────────────────────────────────────────────────────

    def _on_tile_hovered(self, _idx: int) -> None:
        if self._tile_popover is not None:
            return
        if self._focus_mode != "tiles":
            self._focus_mode = "tiles"
            self._topbar.set_selected(None)
            self._tilebar.set_focused(True, scroll=False)
        sound_player.play("cursor")

    def _on_topbar_hovered(self, idx: int) -> None:
        changed = self._focus_mode != "topbar" or self._topbar_index != idx
        if changed:
            self._focus_mode = "topbar"
            self._topbar_index = idx
            self._focus_moved()

    def _on_tile_context_menu(self) -> None:
        self._focus_mode = "tiles"
        self._show_tile_popover()

    def _on_tile_activated(self, context: dict) -> None:
        """A tile (static app or open window) was chosen via gamepad or click."""
        self._active_context = context
        if context['type'] != 'app':
            self.restore_app(context)
            return

        idx = context['id']
        if self._app_manager.is_running(idx):
            logger.info("Restoring application %d", idx)
            self.restore_app(context)
        else:
            logger.info("Launching application %d", idx)
            sound_player.play("select")
            # Minimize other already-running apps to prevent virtual pad interference
            self._arrange_windows()
            trigger = self._apps[idx].get("recall_menu_trigger", BTN_MODE_CLICK)
            self._gamepad.set_app_btn_mode_trigger(trigger)
            self._gamepad.pop_handler(self._handle_pad)
            self._app_manager.launch(idx, self._apps[idx])

    def _on_app_launch_failed(self, idx: int, error: str) -> None:
        logger.warning("Application %d failed to launch: %s", idx, error)
        self._gamepad.push_handler(self._handle_pad)
        InfoDialog(
            message=self.tr("Failed to launch application:\n{0}").format(error),
            on_confirmed=lambda: None,
            gamepad=self._gamepad,
            parent=self,
        )

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Application %d finished – returning to desktop", idx)
        self._close_active_dialog()
        self._tilebar.refresh_status()
        self._wm.refresh_now()
        # Clear active context if it was this app
        if (self._active_context is not None
                and self._active_context.get('type') == 'app'
                and self._active_context.get('id') == idx):
            self._active_context = None
        if not self.isVisible():
            # App exited on its own (crash / self-close) — show desktop now
            self._reactivate_desktop()
        # Some apps (notably Steam) re-enumerate the gamepad on exit,
        # leaving our evdev fd pointing at a dead device with no error.
        # Delay long enough for the kernel to surface the replacement.
        QTimer.singleShot(1000, self._gamepad.refresh)

    # ── Closing an application ─────────────────────────────────────────────

    def _show_tile_popover(self) -> None:
        """Show a context popover above the focused tile."""
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        options: list[tuple[str, object]] = []

        if ctx['type'] == 'app' and not self._app_manager.is_running(ctx['id']):
            options.append((self.tr("Launch"), self._tilebar.select_current))
        else:
            options.append((self.tr("Restore"), self._tilebar.select_current))
            options.append((self.tr("Close"),   self._close_focused_tile))

        popover = TilePopoverMenu(
            options=options,
            gamepad=self._gamepad,
            parent=self,
        )
        self._tile_popover = popover
        popover.closed.connect(self._on_tile_popover_closed)
        popover.show_above(self._tilebar.current_tile())

    def _on_tile_popover_closed(self) -> None:
        self._tile_popover = None

    def _close_focused_tile(self) -> None:
        """Close the application represented by the currently focused tile."""
        app = self._tilebar.current_context()
        if app is not None:
            self.request_close_app(app)

    def _reactivate_desktop(self) -> None:
        """Push our gamepad handler and bring the fullscreen Desktop to the front."""
        self._gamepad.push_handler(self._handle_pad)
        self.showFullScreen()
        self.activateWindow()

    def _restore_desktop_view(self) -> None:
        self._reactivate_desktop()
        # Wayland focus-stealing prevention can ignore Qt's activateWindow
        # when another app (still dying) holds focus. Force Desktop to the
        # top of the stack via KWin scripting.
        self._wm.raise_windows_for_pid_exact(os.getpid())

    def _arrange_windows(self, activate_pid: int | None = None) -> None:
        """Activate windows for activate_pid and minimize all other running apps."""
        all_pids = set(self._app_manager.all_running_pids())
        if activate_pid:
            self._wm.activate_windows_for_pids({activate_pid})
        other_pids = all_pids - ({activate_pid} if activate_pid else set())
        if other_pids:
            self._wm.minimize_windows_for_pids(other_pids)

    def _close_active_dialog(self) -> None:
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending – forcing to close")
            self._confirm_dialog.force_close()
            self._confirm_dialog = None

    # ── Confirmation dialogs ───────────────────────────────────────────────

    def _show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Creates a ConfirmDialog and manages the lifecycle of self._confirm_dialog.

        If a dialog is already open — ignores the call. The on_confirmed
        and on_cancelled callbacks are automatically wrapped to clear
        self._confirm_dialog before passing control.
        """
        if self._confirm_dialog is not None:
            return

        def _wrap(cb: Callable[[], None] | None) -> Callable[[], None]:
            def _inner() -> None:
                self._confirm_dialog = None
                if cb:
                    cb()
            return _inner

        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=_wrap(on_confirmed),
            on_cancelled=_wrap(on_cancelled),
            gamepad=self._gamepad,
            parent=self,
        )

    # ── Top bar actions ────────────────────────────────────────────────────

    def _topbar_action(self, action_type: str) -> None:
        self._action_runner.run(action_type)

    def _open_volume_overlay(self) -> None:
        overlay = VolumeOverlay(self._gamepad, parent=self)
        self._volume_overlay = overlay
        overlay.closed.connect(self._on_volume_closed)

    def _on_volume_closed(self) -> None:
        self._volume_overlay = None
        self._focus_mode = "topbar"
        self._render_focus()
