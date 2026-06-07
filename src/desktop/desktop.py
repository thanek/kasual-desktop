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
from system.window_manager import KWinWindowManager, expand_pid_tree
from ui import styles
from ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard
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

        # Currently active app/window — what BTN_MODE context menu will target
        # {'type': 'app', 'id': idx, 'name': ...} or {'type': 'dyn', 'id': win_id, 'name': ...}
        # dyn contexts also carry 'trigger' (BTN_MODE_CLICK / BTN_MODE_HOLD_1S)
        self._active_context: dict | None                    = None

        self.setWindowTitle("Kasual Desktop")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # Layer-shell surface (Phase 1): keep the Desktop full-screen and above
        # the DE panels under the global layer-shell integration. The Home
        # Overlay (overlay layer) still renders above this. The show/hide state
        # machine rework lands in Phase 2.
        make_layer_surface(
            self,
            layer=Layer.TOP,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.ON_DEMAND,
        )

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

        # Deferred-hide state: the Desktop stays on screen after launching an
        # app until that app's window is actually mapped (see _arm_deferred_hide).
        self._pending_hide_idx: int | None = None
        self._pending_hide_grace_ms = 0
        self._pending_hide_poll = QTimer(self)
        self._pending_hide_poll.setInterval(150)
        self._pending_hide_poll.timeout.connect(self._wm.refresh_now)
        self._pending_hide_guard = QTimer(self)
        self._pending_hide_guard.setSingleShot(True)
        self._pending_hide_guard.timeout.connect(self._force_deferred_hide)
        self._hide_grace = QTimer(self)
        self._hide_grace.setSingleShot(True)
        self._hide_grace.timeout.connect(self._do_deferred_hide)

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
        # Where the close was triggered from decides where Cancel returns to:
        # the Desktop (tile menu, KD visible) or the running app (overlay opened
        # over it, KD hidden). Captured now, before the dialog changes anything.
        from_desktop = self.isVisible()

        def _confirmed() -> None:
            self._restore_desktop_view()
            if app['type'] == 'app':
                idx = app['id']
                self._tilebar.set_static_closing(idx)
                if self._app_manager.is_running(idx):
                    self._app_manager.terminate(idx)
                else:
                    # App was launched via a forwarder (e.g. `steam steam://...`)
                    # whose launcher process has already exited — AppManager has
                    # no live process to kill. Close matching KWin windows instead.
                    self._close_app_windows(idx)
            else:
                self._active_context = None
                self._wm.close_window(app['id'])
                QTimer.singleShot(1000, self._wm.refresh_now)

        def _cancelled() -> None:
            # Cancelling closes the dialog without consequences: return to the
            # context the user came from rather than yanking up the Desktop.
            if from_desktop:
                self._restore_desktop_view()
            else:
                self.restore_app(app)

        self._show_confirm(
            question=self.tr('Are you sure you want to close\n"{0}"?').format(display),
            on_confirmed=_confirmed,
            on_cancelled=_cancelled,
        )

    def _close_app_windows(self, idx: int) -> None:
        """Close all KWin windows belonging to a static app matched by command name.

        Used when AppManager has no live process for the app — e.g. apps started
        via a one-shot forwarder (steam://...) whose launcher exits immediately
        while the real process continues under a different PID.
        """
        cmd = os.path.basename(self._apps[idx]['command']).lower()
        matched = [
            w['id'] for w in self._wm.cached_windows()
            if w.get('resourceClass', '').lower() == cmd
            or os.path.splitext(w.get('desktopFile', '').lower())[0] == cmd
        ]
        logger.info("Closing app %d via KWin windows %s (cmd=%s)", idx, matched, cmd)
        for win_id in matched:
            self._wm.close_window(win_id)
        QTimer.singleShot(1500, self._wm.refresh_now)


    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The Desktop maps under wherever the cursor was left (e.g. after an app
        # exits). Block tile hovers until the mouse actually moves, so a tile
        # under the idle cursor doesn't hijack the selection on reappearance.
        self._tilebar.suppress_hover_until_move()
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

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            # When KWin gives us focus back (e.g. the app we ceded the pad to
            # has closed) and nobody owns the handler stack, reclaim pad control.
            # Edge-triggered on focus gain, so it never fires while an app is
            # foreground (we are not active then). This covers apps launched via
            # a forwarder — e.g. `steam steam://...`, whose launcher process
            # exits immediately, so the normal app_finished path runs too early.
            if self.isActiveWindow() and self._active_context is None \
                    and self._gamepad.top_handler() is None:
                self._reactivate_desktop()

    # ── Tile bar coordination ───────────────────────────────────────────────

    def _check_active_dyn_gone(self) -> None:
        """If the active dynamic window disappeared (closed by the app) → show desktop."""
        ctx = self._active_context
        if ctx is not None and ctx.get('type') == 'dyn':
            if not self._tilebar.has_dynamic_window(ctx['id']):
                self._active_context = None
                # Re-establish gamepad control even when the Desktop window is
                # already visible: restore_app() popped our handler, so a bare
                # visible window would leave the pad unresponsive. Only seize
                # input if nobody else owns it (an open HomeOverlay sits on top
                # of the handler stack and must keep receiving events).
                top = self._gamepad.top_handler()
                if top is None or top == self._handle_pad:
                    self._reactivate_desktop()
                # Some apps (notably Steam) re-enumerate the gamepad when they
                # exit, silently invalidating our evdev fd. Externally-launched
                # (dyn) apps don't go through _on_app_finished, so force the
                # rebind here too — same delay as the AppManager path.
                QTimer.singleShot(1000, self._gamepad.refresh)

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
        key = event.key()
        # Escape in tiles mode with no overlay open → open Home Overlay (same
        # signal as BTN_MODE short press). In topbar mode Escape still falls
        # through to the _KEY_MAP and injects "cancel" to return to tiles.
        if (key == Qt.Key.Key_Escape
                and self._focus_mode == "tiles"
                and self._gamepad.top_handler() == self._handle_pad):
            self._gamepad.btn_mode_pressed.emit()
            return True
        mapped = self._KEY_MAP.get(key)
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
            # launch() reports an immediate failure (e.g. command not found)
            # synchronously via app_launch_failed — _on_app_launch_failed has
            # already reactivated the Desktop and shown the error by the time
            # this returns False. Only arm the deferred hide for a real launch;
            # arming it for a failed one would strand a window-poll + 5 s guard
            # that later hides the Desktop and churns the tile selection.
            if self._app_manager.launch(idx, self._apps[idx]):
                # The Desktop is a top-layer surface and must be hidden for the
                # windowed app to show — but we defer that until the app's window
                # is actually mapped, so the DE desktop never flashes through the
                # start-up gap. Re-shown by _on_app_finished.
                self._arm_deferred_hide(idx)

    # ── Deferred hide on launch ─────────────────────────────────────────────

    def _arm_deferred_hide(self, idx: int) -> None:
        """Hide the Desktop only once the launched app has a mapped window.

        The Desktop is a top-layer surface sitting above the windowed app, so it
        must be hidden for the app to be visible. Hiding it the instant we launch
        would expose the DE desktop underneath for as long as the app takes to
        draw its first frame. Instead we keep the Desktop covering the screen and
        hide it when KWin first reports a window belonging to the app, polling
        the window list quickly meanwhile. A safety timeout hides it anyway, so a
        slow or undetected window never strands us in front of the running app.
        """
        self._cancel_deferred_hide()
        self._pending_hide_idx = idx
        self._pending_hide_grace_ms = int(self._apps[idx].get("launch_hide_grace_ms", 0))
        self._wm.windows_updated.connect(self._on_windows_pending_hide)
        self._pending_hide_poll.start()
        self._pending_hide_guard.start(5000)
        self._wm.refresh_now()

    def _on_windows_pending_hide(self, windows: list[dict]) -> None:
        idx = self._pending_hide_idx
        if idx is None or not self._app_window_present(idx, windows):
            return
        # The app's window is mapped. Stop watching, but give apps that show an
        # intermediate window before their real one (e.g. Steam's bootstrap
        # window vs. Big Picture) an optional grace period to settle, so we
        # don't uncover a half-drawn frame.
        self._stop_pending_watch()
        if self._pending_hide_grace_ms > 0:
            self._hide_grace.start(self._pending_hide_grace_ms)
        else:
            self._do_deferred_hide()

    def _app_window_present(self, idx: int, windows: list[dict]) -> bool:
        """True if `windows` contains a window belonging to launched app `idx`.

        Matched by PID subtree (covers normal child windows), with a resource /
        desktop-file fallback for forwarder launchers like `steam steam://...`
        whose visible window runs under an unrelated PID.
        """
        pid  = self._app_manager.running_pid(idx)
        pids = expand_pid_tree({pid}) if pid else set()
        cmd  = os.path.basename(self._apps[idx]['command']).lower()
        for w in windows:
            wpid = w.get('pid')
            if wpid and wpid in pids:
                return True
            rc = w.get('resourceClass', '').lower()
            df = os.path.splitext(w.get('desktopFile', '').lower())[0]
            if cmd and (rc == cmd or df == cmd):
                return True
        return False

    def _force_deferred_hide(self) -> None:
        """Safety-timeout path: hide the Desktop even if no window was detected."""
        self._stop_pending_watch()
        self._do_deferred_hide()

    def _do_deferred_hide(self) -> None:
        """Hide the Desktop to reveal the now-mapped app."""
        self._pending_hide_idx = None
        if self.isVisible():
            self.hide()

    def _stop_pending_watch(self) -> None:
        """Stop the window poll/guard and disconnect (keeps a queued grace hide)."""
        self._pending_hide_poll.stop()
        self._pending_hide_guard.stop()
        try:
            self._wm.windows_updated.disconnect(self._on_windows_pending_hide)
        except TypeError:
            pass

    def _cancel_deferred_hide(self) -> None:
        """Tear down the deferred-hide watcher entirely without hiding the Desktop."""
        if self._pending_hide_idx is None:
            return
        self._pending_hide_idx = None
        self._stop_pending_watch()
        self._hide_grace.stop()

    def _on_app_launch_failed(self, idx: int, error: str) -> None:
        logger.warning("Application %d failed to launch: %s", idx, error)
        # Launch failed before any window: drop the pending hide so the Desktop
        # stays up for the error dialog instead of vanishing.
        self._cancel_deferred_hide()
        # _on_tile_activated set the active context optimistically when the tile
        # was chosen; the app never started, so clear it (if it is still ours).
        # Otherwise BTN_MODE would target the never-launched app instead of
        # opening the general Home Overlay.
        if (self._active_context is not None
                and self._active_context.get('type') == 'app'
                and self._active_context.get('id') == idx):
            self._active_context = None
        self._reactivate_desktop()
        InfoDialog(
            message=self.tr("Failed to launch application:\n{0}").format(error),
            on_confirmed=lambda: None,
            gamepad=self._gamepad,
            parent=self,
        )

    def _on_app_finished(self, idx: int) -> None:
        logger.info("Application %d finished – returning to desktop", idx)
        # App exited (possibly before its window ever mapped) — stop waiting to
        # hide the Desktop, otherwise we would hide onto a closed app.
        self._cancel_deferred_hide()
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

        if ctx['type'] == 'app' and not self._tilebar.is_tile_running(ctx['id']):
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
        """Restore Desktop input control and bring it to the front.

        Idempotent: push_handler() moves our handler to the top if it is already
        present, and the window is only re-shown when actually hidden. The
        BTN_MODE trigger is reset to the Desktop default so no app-specific
        HOLD_1S setting lingers after the app is gone.
        """
        self._gamepad.set_app_btn_mode_trigger(BTN_MODE_CLICK)
        self._gamepad.push_handler(self._handle_pad)
        if not self.isVisible():
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

    def confirm(self, question: str, on_confirmed: Callable[[], None]) -> None:
        """Public entry for confirmable actions triggered from outside the
        Desktop (e.g. the Home Overlay's system actions), so the dialog is
        tracked in self._confirm_dialog exactly like the topbar's."""
        self._show_confirm(question=question, on_confirmed=on_confirmed)

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
