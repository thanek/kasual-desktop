import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from domain.catalog.live_catalog import LiveCatalog
from domain.shell.desktop_state import DesktopState
from domain.input.vocabulary import Event
from domain.input.pad_control import PadControl
from infrastructure.qt.overlays.base_overlay import BaseOverlay
from infrastructure.qt.overlays.confirm_dialog import ConfirmDialog
from infrastructure.qt.overlays.info_dialog import InfoDialog
from infrastructure.qt.overlays.tile_popover import TilePopoverMenu
from infrastructure.qt.overlays.tile_color_picker import TileColorPicker
from infrastructure.qt.overlays.volume_overlay import VolumeOverlay
from infrastructure.qt.overlays.brightness_overlay import BrightnessOverlay
from infrastructure.qt.overlays.notifications_overlay import NotificationsOverlay
from infrastructure.qt.overlays.network_overlay import NetworkOverlay
from domain.notifications.center import NotificationCenter
from domain.network import view as network_view
from domain.network.control import NetworkControl
from domain.network.status import NetworkStatus
from domain.system.actions import NETWORK, NOTIFICATIONS
from domain.system.volume import VolumeControl
from domain.system.brightness import BrightnessControl
from domain.system.power_control import PowerControl
from domain.shared.scheduler import Scheduler
from domain.lifecycle.app_control import AppControl
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager
from infrastructure.qt.ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.navigation.focus_navigator import FocusNavigator
from domain.navigation.tile_mover import TileMover
from domain.system.runner import ActionRunner
from domain.menu.entry import CHANGE_COLOR, MOVE, PIN, UNPIN
from domain.menu.item import MenuItem
from domain.menu.palette import TILE_COLORS
from domain.menu.ports import AppPinning, TileColorStore
from domain.menu.tile import tile_management_menu, tile_menu_for
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.shared.text import truncate
from typing import _ProtocolMeta  # type: ignore[attr-defined]
from domain.shell.desktop_view import DesktopView
from domain.shell.desktop_control import DesktopControl
from domain.shell.open_overlays import OpenOverlays
from domain.system.desktop_shell import DesktopShell
from domain.shell.wallpaper import SystemWallpaper
from .tile_bar import TileBar
from .topbar import TopBar

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
    Qt.Key.Key_F2:     Event.MANAGE,
}


class _Meta(type(QWidget), _ProtocolMeta): pass


class Desktop(QWidget, DesktopView, DesktopShell, DesktopControl, metaclass=_Meta):
    """Main environment window — always fullscreen."""

    def __init__(
        self,
        apps: LiveCatalog,
        gamepad: PadControl,
        window_manager: WindowManager,
        wallpaper: SystemWallpaper,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        power: PowerControl,
        scheduler: Scheduler,
        process_manager: ProcessManager,
        notifications: NotificationCenter,
        network_control: NetworkControl,
        overlays: OpenOverlays,
        color_store: TileColorStore,
        app_pinning: AppPinning,
    ):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._wm          = window_manager
        self._system_wallpaper = wallpaper
        self._feedback    = feedback
        self._app_manager = process_manager
        self._volume_control = volume
        self._brightness_control = brightness
        self._power       = power
        self._scheduler   = scheduler
        self._notifications = notifications
        self._network_control = network_control
        self._network_status = NetworkStatus.offline()
        # System-action overlays (volume/brightness/…) are tracked as a group in
        # the domain registry; only the confirm dialog keeps a named handle, for
        # its single-instance guard and the app-ended force-close.
        self._overlays       = overlays
        self._color_store    = color_store
        self._app_pinning    = app_pinning
        self._confirm_dialog = None
        self._tile_popover   = None
        self._color_picker   = None

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

        # Domain coordinators are assembled by the package builder (build_desktop)
        # and injected via attach(); the widget itself stays a pure view. The pad
        # handler identity stays owned here so push/pop on the gamepad stack
        # matches the eventFilter's comparisons.
        self._nav:           'FocusNavigator | None'     = None
        self._lifecycle:     'AppLifecycle | None'       = None
        self._desktop:       'DesktopCoordinator | None' = None
        self._action_runner: 'ActionRunner | None'       = None
        self._tile_mover:    'TileMover | None'          = None

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tilebar.refresh_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = self._load_wallpaper_pixmap()

        self._wm.on_windows_updated(self._tilebar.update_windows)

        # Desktop is not shown at startup — build_desktop wires it via attach(),
        # then it is revealed on the connected_changed(True) signal.

    def attach(
        self,
        nav: FocusNavigator,
        lifecycle: AppLifecycle,
        desktop_coordinator: DesktopCoordinator,
        action_runner: ActionRunner,
        tile_mover: TileMover,
    ) -> None:
        """Inject the domain coordinators assembled by build_desktop and wire the
        orchestration signals. Called once, before the Desktop is ever shown, so
        the widget's handlers — which delegate to these coordinators — never fire
        with them unset."""
        self._nav           = nav
        self._lifecycle     = lifecycle
        self._desktop       = desktop_coordinator
        self._action_runner = action_runner
        self._tile_mover    = tile_mover

        self._tilebar.activated.connect(self._lifecycle.on_tile_activated)
        self._tilebar.windows_changed.connect(self._lifecycle.check_active_dyn_gone)
        self._app_manager.on_finished(
            lambda e: self._lifecycle.on_app_finished(e.idx))
        self._app_manager.on_launch_failed(
            lambda e: self._lifecycle.on_app_launch_failed(e.idx, e.error))

        QApplication.instance().installEventFilter(self)

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def app_manager(self) -> ProcessManager:
        return self._app_manager

    @property
    def app_control(self) -> AppControl:
        """The app-lifecycle coordinator as the Application controller drives it
        (restore/close/current/foreground). Exposed so the wiring root hands the
        coordinator straight to the Application instead of routing through the
        Desktop widget."""
        return self._lifecycle

    def show_desktop(self) -> None:
        """Show the desktop without interrupting the running application."""
        self._desktop.show_desktop()

    def pause(self) -> None:
        """Hide the Desktop without disconnecting the gamepad (minimize to tray)."""
        self._desktop.pause()

    def dismiss_overlays(self) -> None:
        """Cancel every open overlay/dialog (driven when the Home Overlay takes
        over): the registry tears down the group; the confirm handle is among
        them, so its slot just needs clearing. Move mode is not a registered
        overlay (it owns a pushed pad handler), so it is cancelled explicitly."""
        self._overlays.cancel()
        self._confirm_dialog = None
        self._color_picker = None
        if self._tile_mover is not None:
            self._tile_mover.cancel()

    def resume(self) -> None:
        """Restore the Desktop after reconnecting the gamepad — without resetting state."""
        self._desktop.resume()

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

    def close_active_dialog(self) -> None:
        self._close_active_dialog()

    def show_error(self, message: str) -> None:
        InfoDialog(
            message=message,
            on_confirmed=lambda: None,
            gamepad=self._gamepad,
            feedback=self._feedback,
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

    def _load_wallpaper_pixmap(self) -> 'QPixmap | None':
        """Render the domain wallpaper (a path) into a QPixmap for painting.

        The domain decides *which* image is the background (the system
        wallpaper); turning it into pixels is this view's concern.
        """
        from PyQt6.QtGui import QPixmap
        wallpaper = self._system_wallpaper.current()
        if wallpaper is None:
            return None
        return QPixmap(wallpaper.image_path)

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
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            # When KWin gives us focus back (e.g. the app we ceded the pad to
            # has closed) delegate the reactivate decision to the domain layer.
            # Edge-triggered on focus gain, so it never fires while an app is
            # foreground (we are not active then). This covers apps launched via
            # a forwarder — e.g. `steam steam://...`, whose launcher process
            # exits immediately, so the normal app_finished path runs too early.
            self._lifecycle.on_focus_gained()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        key = event.key()
        # Escape in tiles mode with no overlay open → open Home Overlay via
        # domain event (ESCAPE_HOME). The top_handler guard restricts this to
        # when the Desktop itself owns the pad: layer-shell overlays keep the
        # Desktop the active Qt window (keyboard=NONE, no activateWindow), so
        # this filter still fires while one is open — but then their handler is
        # on top and Escape must fall through to _KEY_MAP → CANCEL, which they
        # handle. In topbar mode Escape likewise falls through to "cancel" to
        # return to tiles.
        if (key == Qt.Key.Key_Escape
                and self._nav.in_tiles
                and self._gamepad.top_handler() == self._handle_pad):
            self._gamepad.inject(Event.ESCAPE_HOME)
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

        The menu (which items, their running-state rule) and the behaviour of the
        chosen item are the domain's: `tile_menu_for` composes it and the lifecycle
        coordinator's `dispatch_tile_action` performs it. Here we only render and
        position the popover and report activation.
        """
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        popover = TilePopoverMenu(
            items=tile_menu_for(ctx, lambda idx: self._tilebar.is_tile_running(idx, self._tilebar.last_windows)),
            on_select=self._lifecycle.dispatch_tile_action,
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self,
        )
        self._tile_popover = popover
        self._overlays.register(popover)
        popover.closed.connect(self._on_tile_popover_closed)
        popover.show_above(self._tilebar.current_tile())

    def _on_tile_popover_closed(self) -> None:
        self._overlays.forget(self._tile_popover)
        self._tile_popover = None

    # ── Tile Management Popover (Start button) ─────────────────────────────

    def _show_tile_management_popover(self) -> None:
        """Show the Start-button management popover above the focused tile.

        The menu differs by tile kind (`tile_management_menu`): a configured app
        tile offers move/recolour, an open-window tile offers *Pin to menu*. Reuses
        the generic popover widget; the chosen item's behaviour is the domain's
        (`TileMover`) or the pin adapter's."""
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        popover = TilePopoverMenu(
            items=tile_management_menu(ctx),
            on_select=self._on_manage_select,
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self,
        )
        self._tile_popover = popover
        self._overlays.register(popover)
        popover.closed.connect(self._on_tile_popover_closed)
        popover.show_above(self._tilebar.current_tile())

    def _on_manage_select(self, item: MenuItem) -> None:
        if item.action == MOVE:
            self._tile_mover.start()
        elif item.action == CHANGE_COLOR:
            self._show_color_picker()
        elif item.action == PIN:
            self._pin_window(item.target)
        elif item.action == UNPIN:
            self._unpin_app(item.target)

    def _pin_window(self, target) -> None:
        """Promote the focused open-window tile to a persistent app tile.

        Resolves the window behind *target*, lets the pin adapter write its Kasual
        ``.desktop`` entry, and on success adds the tile live. A window that cannot
        be resolved to a launchable command (e.g. no source ``.desktop``) fails
        quietly with a back cue rather than a phantom tile."""
        window = self._tilebar.window_for(target.window_id)
        app = self._app_pinning.pin(window) if window is not None else None
        if app is None:
            self._feedback.play(Cue.EXIT)
            return
        self._tilebar.pin_window(app, target.window_id)
        self._feedback.play(Cue.SELECT)

    def _unpin_app(self, target) -> None:
        """Confirm, then remove the focused app tile from the menu — the reverse of
        pinning. The index is captured for the confirm callback: the dialog is modal
        so the focus cannot move underneath it (mirrors the colour picker)."""
        index = target.index
        self._show_confirm(
            question=translate("Desktop", 'Are you sure you want to unpin\n"{0}"?')
                .format(truncate(target.name, 40)),
            on_confirmed=lambda: self._do_unpin(index),
        )

    def _do_unpin(self, index: int) -> None:
        """Delete the persisted ``.desktop`` (so it stays gone after a restart) and
        drop the tile live; a still-running app reappears as a dynamic open-window
        tile, an idle one simply disappears."""
        self._app_pinning.unpin(index)
        self._tilebar.unpin_app(index)
        self._feedback.play(Cue.SELECT)

    def _show_color_picker(self) -> None:
        """Open the palette picker for the focused app tile.

        The chosen colour is applied to the tile and persisted; cancelling (B /
        Escape / backdrop / BTN_MODE) leaves it unchanged. The capture of the tile
        index is safe: the picker is modal, so the focus cannot move underneath it."""
        if self._color_picker is not None or not self._tilebar.current_is_app():
            return
        index = self._tilebar.current_app_index()

        def _on_chosen(color: str) -> None:
            self._forget_color_picker()
            self._tilebar.set_app_color(index, color)
            self._color_store.set_color(index, color)

        self._color_picker = TileColorPicker(
            colors=TILE_COLORS,
            selected=self._tilebar.current_app_color(),
            on_select=_on_chosen,
            on_cancel=self._forget_color_picker,
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self,
        )
        self._overlays.register(self._color_picker)

    def _forget_color_picker(self) -> None:
        self._overlays.forget(self._color_picker)
        self._color_picker = None

    def _close_active_dialog(self) -> None:
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending – forcing to close")
            self._confirm_dialog.cancel()
            self._forget_confirm()

    def _forget_confirm(self) -> None:
        """Drop the confirm dialog from the registry and clear its slot."""
        self._overlays.forget(self._confirm_dialog)
        self._confirm_dialog = None

    # ── Confirmation dialogs ───────────────────────────────────────────────

    def _show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        """Open a ConfirmDialog, ignoring the call if one is already up.

        The callbacks are wrapped to forget the dialog before handing control on,
        so its slot and registry entry clear on whichever button is pressed.
        """
        if self._confirm_dialog is not None:
            return

        def _wrap(cb: Callable[[], None] | None) -> Callable[[], None]:
            def _inner() -> None:
                self._forget_confirm()
                if cb:
                    cb()
            return _inner

        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=_wrap(on_confirmed),
            on_cancelled=_wrap(on_cancelled),
            gamepad=self._gamepad,
            feedback=self._feedback,
            parent=self,
        )
        self._overlays.register(self._confirm_dialog)

    # ── Top bar actions ────────────────────────────────────────────────────

    def _topbar_action(self, action_type: str) -> None:
        self._action_runner.run(action_type)

    def _present(self, overlay: BaseOverlay) -> None:
        """Track a freshly opened top-bar overlay; return focus to the bar when
        it closes. The registry then pauses/resumes/cancels it with the group."""
        self._overlays.register(overlay)
        overlay.closed.connect(lambda: self._on_overlay_closed(overlay))

    def _on_overlay_closed(self, overlay: BaseOverlay) -> None:
        self._overlays.forget(overlay)
        self._nav.focus_topbar()

    def open_volume_overlay(self) -> None:
        self._present(VolumeOverlay(self._gamepad, self._volume_control, self._feedback, parent=self))

    def open_brightness_overlay(self) -> None:
        self._present(BrightnessOverlay(self._gamepad, self._brightness_control, self._feedback, parent=self))

    def refresh_notification_badge(self) -> None:
        """Sync the notifications button badge to the unread count in memory."""
        self._topbar.set_badge(NOTIFICATIONS, self._notifications.unread_count)

    def update_network_status(self, status: NetworkStatus) -> None:
        """Store the latest network status and reflect its kind in the top-bar
        icon (driven by the NetworkMonitor; the popup reads the stored status)."""
        self._network_status = status
        self._topbar.set_action_icon(NETWORK, network_view.icon_for(status.kind))

    def open_network_overlay(self) -> None:
        self._present(NetworkOverlay(
            self._gamepad, self._network_status, self._network_control,
            self._feedback, parent=self,
        ))

    def open_notifications_overlay(self) -> None:
        # The overlay reads the unread tally (to highlight new rows) as it builds;
        # only then do we clear it and drop the badge — the user has now seen them.
        overlay = NotificationsOverlay(self._gamepad, self._notifications, self._feedback, parent=self)
        self._notifications.mark_all_read()
        self.refresh_notification_badge()
        self._present(overlay)
