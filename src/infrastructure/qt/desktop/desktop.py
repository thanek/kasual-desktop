import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from domain.catalog.app import App
from domain.shell.desktop_state import DesktopState
from domain.input.vocabulary import Event
from domain.catalog.target import AppTarget, Target
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.overlays.base_overlay import BaseOverlay
from infrastructure.qt.overlays.confirm_dialog import ConfirmDialog
from infrastructure.qt.overlays.info_dialog import InfoDialog
from infrastructure.qt.overlays.tile_popover import TilePopoverMenu
from infrastructure.qt.overlays.volume_overlay import VolumeOverlay
from infrastructure.system.app_manager import AppManager
from infrastructure.system.power import SystemdPowerControl
from infrastructure.system.volume import PactlVolumeControl
from infrastructure.system.window_manager import KWinWindowManager
from infrastructure.qt.ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard
from domain.system.action_view import make_action_confirm
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.lifecycle.prompts import LocalizedPrompts
from domain.navigation.focus_navigator import FocusNavigator
from domain.system.actions import ActionDeps
from domain.system.runner import ActionRunner
from domain.menu.entry import CLOSE, LAUNCH, RESTORE
from domain.menu.tile import compose_tile_menu
from infrastructure.audio.feedback import SoundFeedback
from infrastructure.qt.scheduler import QtScheduler
from typing import _ProtocolMeta  # type: ignore[attr-defined]
from domain.shell.desktop_view import DesktopView
from domain.shell.session_collaborators import SessionView
from domain.system.desktop_shell import DesktopShell
from .deferred_hide import DeferredHide
from .tile_bar import TileBar
from .topbar import TopBar
from .wallpaper import KdeWallpaperLoader

logger = logging.getLogger(__name__)

# Keyboard keys → navigation events, so a keyboard drives the same handler stack
# (injected via the gamepad). Translating Qt key codes is an input-edge concern;
# FocusNavigator itself deals only in abstract domain events.
_KEY_MAP = {
    Qt.Key.Key_Left:   Event.LEFT,
    Qt.Key.Key_Right:  Event.RIGHT,
    Qt.Key.Key_Up:     Event.UP,
    Qt.Key.Key_Down:   Event.DOWN,
    Qt.Key.Key_Return: Event.SELECT,
    Qt.Key.Key_Enter:  Event.SELECT,
    Qt.Key.Key_Escape: Event.CANCEL,
    Qt.Key.Key_Q:      Event.CLOSE,
}


class _Meta(type(QWidget), _ProtocolMeta): pass


class Desktop(QWidget, DesktopView, DesktopShell, SessionView, metaclass=_Meta):
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

        # Desktop visibility + paused + what the BTN_MODE menu targets (foreground).
        # The foreground is shared by reference with the AppLifecycle coordinator.
        self._state      = DesktopState()
        self._foreground = self._state.foreground

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

        self._feedback = SoundFeedback()
        self._nav = FocusNavigator(
            self._tilebar, self._topbar,
            on_tile_menu=self._show_tile_popover, feedback=self._feedback,
        )

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
            scheduler=QtScheduler(),
            feedback=self._feedback,
            prompts=LocalizedPrompts(),
        )
        # Coordinates show/pause/resume of the Desktop surface (this widget = view).
        self._desktop = DesktopCoordinator(
            state=self._state, view=self, feedback=self._feedback,
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
            ActionDeps(desktop=self, power=SystemdPowerControl()),
            make_action_confirm(
                lambda q, cb: self._show_confirm(question=q, on_confirmed=cb)
            ),
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
        self._desktop.show_desktop()

    def pause(self) -> None:
        """Hide the Desktop without disconnecting the gamepad (minimize to tray)."""
        self._desktop.pause()

    def resume(self) -> None:
        """Restore the Desktop after reconnecting the gamepad — without resetting state."""
        self._desktop.resume()

    @property
    def _active_overlays(self) -> list[BaseOverlay]:
        """Active overlays (those that can be paused/resumed)."""
        return [o for o in (self._volume_overlay, self._confirm_dialog) if o is not None]

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

    def take_input(self) -> None:
        self._gamepad.push_handler(self._handle_pad)

    def release_input(self) -> None:
        self._gamepad.pop_handler(self._handle_pad)

    def refresh_windows(self) -> None:
        self._wm.refresh_now()

    def pause_overlays(self) -> None:
        for overlay in self._active_overlays:
            overlay.pause()

    def resume_overlays(self) -> None:
        for overlay in self._active_overlays:
            overlay.resume()

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
        mapped = _KEY_MAP.get(key)
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
        """Show a context popover above the focused tile.

        The whole menu (which items, their labels) is composed by
        domain.compose_tile_menu; here we only render it and dispatch the chosen
        item's action.
        """
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        is_running = (
            self._tilebar.is_tile_running(ctx.index)
            if isinstance(ctx, AppTarget) else True
        )
        popover = TilePopoverMenu(
            items=compose_tile_menu(ctx, is_running),
            on_select=self._dispatch_tile,
            gamepad=self._gamepad,
            parent=self,
        )
        self._tile_popover = popover
        popover.closed.connect(self._on_tile_popover_closed)
        popover.show_above(self._tilebar.current_tile())

    def _on_tile_popover_closed(self) -> None:
        self._tile_popover = None

    def _dispatch_tile(self, item) -> None:
        """Perform the behaviour for an activated tile Popover item."""
        if item.action in (LAUNCH, RESTORE):
            self._tilebar.select_current()
        elif item.action == CLOSE:
            self._close_focused_tile()

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
