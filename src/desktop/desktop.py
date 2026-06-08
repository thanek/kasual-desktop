import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from audio import sound_player
from domain.app import App
from domain.foreground import ForegroundState
from domain.target import AppTarget, Target
from input.gamepad_watcher import GamepadWatcher
from overlays.base_overlay import BaseOverlay
from overlays.confirm_dialog import ConfirmDialog
from overlays.info_dialog import InfoDialog
from overlays.tile_popover import TilePopoverMenu
from overlays.volume_overlay import VolumeOverlay
from system.app_manager import AppManager
from system.system_actions import ActionDeps, ActionRunner
from system.volume import PactlVolumeControl
from system.window_manager import KWinWindowManager
from ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard
from .deferred_hide import DeferredHide
from .lifecycle import AppLifecycle
from .navigation import FocusNavigator
from .tile_bar import TileBar
from .topbar import TopBar
from .wallpaper import KdeWallpaperLoader

logger = logging.getLogger(__name__)


class Desktop(QWidget):
    """Main environment window — always fullscreen."""

    def __init__(
        self,
        apps: list[App],
        gamepad: GamepadWatcher,
        window_manager: KWinWindowManager,
    ):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._wm          = window_manager
        self._app_manager = AppManager(self)
        self._volume_control = PactlVolumeControl()
        self._confirm_dialog = None
        self._volume_overlay = None
        self._tile_popover   = None
        self._is_paused      = False

        # What the BTN_MODE menu will target: an AppTarget / WindowTarget, or
        # idle on the bare Desktop. Owns its own clear-on-finish/fail transitions.
        self._foreground = ForegroundState()

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
        self._tilebar.tile_hovered.connect(self._on_tile_hovered)
        self._tilebar.tile_context_menu.connect(self._on_tile_context_menu)
        main.addWidget(self._tilebar)
        main.addStretch(1)

        self._nav = FocusNavigator(self._tilebar, self._topbar, on_tile_menu=self._show_tile_popover)

        # The Desktop stays on screen after launching an app until that app's
        # window is actually mapped, then hides to reveal it.
        self._deferred_hide = DeferredHide(
            self._wm, self._app_manager, self._apps, on_hide=self.hide
        )
        # App launch/restore/close/exit orchestration lives off the widget in a
        # testable coordinator; the Desktop is just its DesktopView. The pad
        # handler identity stays owned here so push/pop on the gamepad stack
        # matches the eventFilter's comparisons.
        self._lifecycle = AppLifecycle(
            view=self,
            gamepad=self._gamepad,
            window_manager=self._wm,
            app_manager=self._app_manager,
            apps=self._apps,
            foreground=self._foreground,
            deferred_hide=self._deferred_hide,
            tilebar=self._tilebar,
            pad_handler=self._handle_pad,
        )
        self._tilebar.activated.connect(self._lifecycle.on_tile_activated)
        self._tilebar.windows_changed.connect(self._lifecycle.check_active_dyn_gone)
        self._app_manager.app_finished.connect(self._lifecycle.on_app_finished)
        self._app_manager.app_launch_failed.connect(self._lifecycle.on_app_launch_failed)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tilebar.refresh_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = KdeWallpaperLoader().load()

        self._action_runner = ActionRunner(
            ActionDeps(desktop=self),
            lambda q, cb: self._show_confirm(question=q, on_confirmed=cb),
        )

        self._wm.windows_updated.connect(self._tilebar.update_windows)

        QApplication.instance().installEventFilter(self)

        # Desktop is not shown at startup — we wait for the connected_changed(True) signal

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def app_manager(self) -> AppManager:
        return self._app_manager

    def show_desktop(self) -> None:
        """Show the desktop without interrupting the running application."""
        self._foreground.clear()
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

    def current_app(self) -> Target | None:
        """Returns the currently active foreground Target, or None if on desktop."""
        return self._foreground.current

    def restore_app(self, target: Target) -> None:
        """Bring an already-running app back to the foreground (public API used
        by the Home Overlay). Delegates to the lifecycle coordinator."""
        self._lifecycle.restore_app(target)

    def request_close_app(self, target: Target) -> None:
        """Ask to close an app, with a confirm dialog (public API used by the
        Home Overlay and the tile popover). Delegates to the coordinator."""
        self._lifecycle.request_close_app(target)

    # ── DesktopView port (driven by AppLifecycle) ───────────────────────────

    def is_visible(self) -> bool:
        return self.isVisible()

    def show_fullscreen(self) -> None:
        self.showFullScreen()

    def activate(self) -> None:
        self.activateWindow()

    def hide_view(self) -> None:
        self.hide()

    def close_active_dialog(self) -> None:
        self._close_active_dialog()

    def show_error(self, message: str) -> None:
        InfoDialog(
            message=message,
            on_confirmed=lambda: None,
            gamepad=self._gamepad,
            parent=self,
        )

    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        self._show_confirm(question, on_confirmed, on_cancelled)

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
            if self.isActiveWindow() and self._foreground.is_idle() \
                    and self._gamepad.top_handler() is None:
                self._lifecycle.reactivate_desktop()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        key = event.key()
        # Escape in tiles mode with no overlay open → open Home Overlay (same
        # signal as BTN_MODE short press). In topbar mode Escape still falls
        # through to the key map and injects "cancel" to return to tiles.
        if (key == Qt.Key.Key_Escape
                and self._nav.in_tiles
                and self._gamepad.top_handler() == self._handle_pad):
            self._gamepad.btn_mode_pressed.emit()
            return True
        mapped = self._nav.key_event(key)
        if mapped:
            self._gamepad.inject(mapped)
            return True
        return False

    def _handle_pad(self, event: str) -> None:
        # Thin wrapper kept on the Desktop so its identity stays stable on the
        # gamepad handler stack (push/pop/compare); the logic lives in the nav.
        self._nav.handle_pad(event)

    # ── Tile actions ───────────────────────────────────────────────────────

    def _on_tile_hovered(self, _idx: int) -> None:
        if self._tile_popover is not None:
            return
        self._nav.hover_tiles()

    def _on_topbar_hovered(self, idx: int) -> None:
        self._nav.hover_topbar(idx)

    def _on_tile_context_menu(self) -> None:
        self._nav.focus_tiles()
        self._show_tile_popover()

    # ── Closing an application ─────────────────────────────────────────────

    def _show_tile_popover(self) -> None:
        """Show a context popover above the focused tile."""
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        options: list[tuple[str, object]] = []

        if isinstance(ctx, AppTarget) and not self._tilebar.is_tile_running(ctx.index):
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

    def open_volume_overlay(self) -> None:
        overlay = VolumeOverlay(self._gamepad, self._volume_control, parent=self)
        self._volume_overlay = overlay
        overlay.closed.connect(self._on_volume_closed)

    def _on_volume_closed(self) -> None:
        self._volume_overlay = None
        self._nav.focus_topbar()
