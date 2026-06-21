"""Main desktop widget for Windows - brings TopBar + TileBar together."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, _ProtocolMeta

from PyQt6.QtCore import Qt, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QPainter, QColor, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from domain.catalog.live_catalog import LiveCatalog
from domain.input.vocabulary import Event
from domain.input.pad_control import PadControl
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager
from domain.menu.item import MenuItem
from domain.network.control import NetworkControl
from domain.network.status import NetworkStatus
from domain.notifications.center import NotificationCenter
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.shell.desktop_control import DesktopControl
from domain.shell.desktop_state import DesktopState
from domain.shell.desktop_view import DesktopView
from domain.shell.open_overlays import OpenOverlays
from domain.shell.wallpaper import SystemWallpaper
from domain.shared.feedback import Feedback, Cue
from domain.system.brightness import BrightnessControl
from domain.system.desktop_shell import DesktopShell
from domain.system.runner import ActionRunner
from domain.system.volume import VolumeControl
from domain.menu.palette import TILE_COLORS

from .topbar import WindowsTopBar
from .tile_bar import WindowsTileBar
from .home_overlay import WindowsHomeOverlay
from .volume_overlay import VolumeOverlay
from .brightness_overlay import BrightnessOverlay
from .network_overlay import NetworkOverlay
from .notifications_overlay import NotificationsOverlay
from .confirm_dialog import ConfirmDialog

if TYPE_CHECKING:
    from domain.navigation.focus_navigator import FocusNavigator
    from domain.navigation.tile_mover import TileMover
    from domain.lifecycle.app_lifecycle import AppLifecycle

logger = logging.getLogger(__name__)

_KEY_MAP = {
    Qt.Key.Key_Left:   Event.LEFT,
    Qt.Key.Key_Right: Event.RIGHT,
    Qt.Key.Key_Up:     Event.UP,
    Qt.Key.Key_Down:   Event.DOWN,
    Qt.Key.Key_Return: Event.SELECT,
    Qt.Key.Key_Enter:  Event.SELECT,
    Qt.Key.Key_Escape: Event.CANCEL,
    Qt.Key.Key_Q:      Event.CLOSE,
    Qt.Key.Key_F2:     Event.MANAGE,
}


class _Meta(type(QWidget), _ProtocolMeta): pass


class WindowsDesktop(QWidget, DesktopView, DesktopShell, DesktopControl, metaclass=_Meta):
    """Main desktop widget for Windows - fullscreen shell."""

    def __init__(
        self,
        apps: LiveCatalog,
        gamepad: PadControl,
        window_manager: WindowManager,
        wallpaper: SystemWallpaper,
        feedback: Feedback,
        volume: VolumeControl,
        brightness: BrightnessControl,
        process_manager: ProcessManager,
        notifications: NotificationCenter,
        network_control: NetworkControl,
        overlays: OpenOverlays,
        color_store,
        app_pinning,
        parent=None,
    ):
        super().__init__(parent)
        self._apps = apps
        self._gamepad = gamepad
        self._wm = window_manager
        self._system_wallpaper = wallpaper
        self._feedback = feedback
        self._volume_control = volume
        self._brightness_control = brightness
        self._app_manager = process_manager
        self._notifications = notifications
        self._network_control = network_control
        self._overlays = overlays
        self._color_store = color_store
        self._app_pinning = app_pinning
        self._network_status = NetworkStatus.offline()
        self._confirm_dialog = None
        self._tile_popover = None
        self._color_picker = None
        self._shell_window = None

        self._state = DesktopState()
        self._foreground = self._state.foreground

        self.setWindowTitle("Kasual Desktop")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self._topbar = WindowsTopBar()
        self._topbar.action_triggered.connect(self._topbar_action)
        self._topbar.button_hovered.connect(self._on_topbar_hovered)
        main.addWidget(self._topbar)
        main.addStretch(1)

        self._tilebar = WindowsTileBar(self._apps, self._app_manager)
        self._tilebar.tile_hovered.connect(self._on_tile_hovered)
        self._tilebar.tile_context_menu.connect(self._on_tile_context_menu)
        main.addWidget(self._tilebar)
        main.addStretch(1)

        self._nav: 'FocusNavigator | None' = None
        self._lifecycle: 'AppLifecycle | None' = None
        self._desktop: 'DesktopCoordinator | None' = None
        self._action_runner: 'ActionRunner | None' = None
        self._tile_mover: 'TileMover | None' = None

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tilebar.refresh_status)
        self._status_timer.start(500)

        self._wallpaper: QPixmap | None = self._load_wallpaper_pixmap()

        self._wm.on_windows_updated(self._tilebar.update_windows)

    def attach(
        self,
        nav: 'FocusNavigator',
        lifecycle: 'AppLifecycle',
        desktop_coordinator: 'DesktopCoordinator',
        action_runner: 'ActionRunner',
        tile_mover: 'TileMover',
    ) -> None:
        self._nav = nav
        self._lifecycle = lifecycle
        self._desktop = desktop_coordinator
        self._action_runner = action_runner
        self._tile_mover = tile_mover

        self._tilebar.activated.connect(self._lifecycle.on_tile_activated)
        self._tilebar.windows_changed.connect(self._lifecycle.check_active_dyn_gone)
        self._app_manager.on_finished(
            lambda e: self._lifecycle.on_app_finished(e.idx))
        self._app_manager.on_launch_failed(
            lambda e: self._lifecycle.on_app_launch_failed(e.idx, e.error))

        QApplication.instance().installEventFilter(self)

    @property
    def app_manager(self) -> ProcessManager:
        return self._app_manager

    @property
    def app_control(self):
        return self._lifecycle

    def show_desktop(self) -> None:
        self._desktop.show_desktop()

    def pause(self) -> None:
        self._desktop.pause()

    def dismiss_overlays(self) -> None:
        self._overlays.cancel()
        self._confirm_dialog = None
        self._color_picker = None
        if self._tile_mover is not None:
            self._tile_mover.cancel()

    def resume(self) -> None:
        if self._shell_window:
            self._shell_window.showFullScreen()
            self._shell_window.raise_()
            self._shell_window.activateWindow()
        self._desktop.resume()

    def is_visible(self) -> bool:
        return self.isVisible()

    def show_fullscreen(self) -> None:
        self.showFullScreen()

    def activate(self) -> None:
        self.activateWindow()

    def set_shell_window(self, shell_window) -> None:
        self._shell_window = shell_window

    def hide_view(self) -> None:
        if self._shell_window:
            self._shell_window.showMinimized()
        else:
            self.hide()

    def close_active_dialog(self) -> None:
        self._close_active_dialog()

    def show_error(self, message: str) -> None:
        logger.info("Show error (TODO): %s", message)

    def show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        self._show_confirm(question, on_confirmed, on_cancelled)

    def take_input(self) -> None:
        self._gamepad.push_handler(self._handle_pad)

    def release_input(self) -> None:
        self._gamepad.pop_handler(self._handle_pad)

    def refresh_windows(self) -> None:
        self._wm.refresh_now()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._tilebar.suppress_hover_until_move()
        QTimer.singleShot(0, self._tilebar.center_current)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_tilebar'):
            QTimer.singleShot(0, self._tilebar.center_current)

    def _load_wallpaper_pixmap(self) -> QPixmap | None:
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
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#0b140e"))

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape and self._gamepad.top_handler() == self._handle_pad:
            self._gamepad.inject(Event.ESCAPE_HOME)
            return True
        mapped = _KEY_MAP.get(key)
        if mapped:
            self._gamepad.inject(mapped)
            return True
        return False

    def _handle_pad(self, event: str) -> None:
        if self._nav:
            self._nav.handle_pad(event)

    def _on_tile_hovered(self, idx: int) -> None:
        if self._tile_popover is not None:
            return
        if self._nav:
            self._nav.hover_tiles()

    def _on_topbar_hovered(self, idx: int) -> None:
        if self._nav:
            self._nav.hover_topbar(idx)

    def _on_tile_context_menu(self) -> None:
        if self._nav:
            self._nav.focus_tiles()
        self._show_tile_popover()

    def _close_active_dialog(self) -> None:
        if self._confirm_dialog is not None:
            logger.warning("Dialog window still active after app ending - forcing close")
            self._confirm_dialog.cancel()
            self._forget_confirm()

    def _forget_confirm(self) -> None:
        self._overlays.forget(self._confirm_dialog)
        self._confirm_dialog = None

    def _show_tile_popover(self) -> None:
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        from domain.menu.tile import tile_menu_for
        items = tile_menu_for(ctx, lambda idx: self._tilebar.is_tile_running(idx, self._tilebar.last_windows))
        popover = _TilePopoverMenu(
            items=items,
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

    def _show_tile_management_popover(self) -> None:
        ctx = self._tilebar.current_context()
        if ctx is None:
            return
        from domain.menu.tile import tile_management_menu
        items = tile_management_menu(ctx)
        popover = _TilePopoverMenu(
            items=items,
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
        from domain.menu.entry import MOVE, CHANGE_COLOR, PIN, UNPIN
        if item.action == MOVE:
            self._tile_mover.start()
        elif item.action == CHANGE_COLOR:
            self._show_color_picker()
        elif item.action == PIN:
            self._pin_window(item.target)
        elif item.action == UNPIN:
            self._unpin_app(item.target)

    def _pin_window(self, target) -> None:
        logger.info("TODO: Pin window not implemented on Windows")
        self._feedback.play(Cue.EXIT)

    def _unpin_app(self, target) -> None:
        index = target.index
        self._show_confirm(
            question=f"Unpin {target.name}?",
            on_confirmed=lambda: self._do_unpin(index),
        )

    def _do_unpin(self, index: int) -> None:
        logger.info("TODO: Unpin app not implemented on Windows")
        self._feedback.play(Cue.SELECT)

    def _show_color_picker(self) -> None:
        if self._color_picker is not None or not self._tilebar.current_is_app():
            return
        logger.info("TODO: Color picker not implemented on Windows")
        self._forget_color_picker()

    def _forget_color_picker(self) -> None:
        self._overlays.forget(self._color_picker)
        self._color_picker = None

    def _show_confirm(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None] | None = None,
    ) -> None:
        if self._confirm_dialog is not None:
            return

        def _wrap(cb):
            def _inner():
                self._forget_confirm()
                if cb:
                    cb()
            return _inner

        self._confirm_dialog = ConfirmDialog(
            question=question,
            on_confirmed=_wrap(on_confirmed),
            on_cancelled=_wrap(on_cancelled),
            parent=self,
        )
        self._overlays.register(self._confirm_dialog)

    def _topbar_action(self, action_type: str) -> None:
        if self._action_runner:
            self._action_runner.run(action_type)

    def _present(self, overlay) -> None:
        self._overlays.register(overlay)
        overlay.closed.connect(lambda: self._on_overlay_closed(overlay))

    def _on_overlay_closed(self, overlay) -> None:
        self._overlays.forget(overlay)
        if self._nav:
            self._nav.focus_topbar()

    def open_volume_overlay(self) -> None:
        self._present(VolumeOverlay(self._gamepad, self._volume_control, self._feedback, parent=self))

    def open_brightness_overlay(self) -> None:
        self._present(BrightnessOverlay(self._gamepad, self._brightness_control, self._feedback, parent=self))

    def refresh_notification_badge(self) -> None:
        from domain.system.actions import NOTIFICATIONS
        self._topbar.set_badge(NOTIFICATIONS, self._notifications.unread_count)

    def update_network_status(self, status: NetworkStatus) -> None:
        self._network_status = status
        from domain.network import view as network_view
        from domain.system.actions import NETWORK
        self._topbar.set_action_icon(NETWORK, network_view.icon_for(status.kind))

    def open_network_overlay(self) -> None:
        self._present(NetworkOverlay(self._gamepad, self._network_status, self._network_control, self._feedback, parent=self))

    def open_notifications_overlay(self) -> None:
        overlay = NotificationsOverlay(self._gamepad, self._notifications, self._feedback, parent=self)
        self._notifications.mark_all_read()
        self.refresh_notification_badge()
        self._present(overlay)


class _TilePopoverMenu(QWidget):
    """Simple tile popover for Windows - mirrors Linux version."""

    closed = pyqtSignal()

    def __init__(self, items, on_select, gamepad, feedback, parent=None):
        super().__init__(parent)
        self._items = items
        self._on_select = on_select
        self._gamepad = gamepad
        self._feedback = feedback
        self._selected = 0

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self) -> None:
        from .home_overlay import _home_menu_item_normal, _home_menu_item_selected
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        self._card = QWidget()
        self._card.setStyleSheet("""
            background-color: #2e3440;
            border-radius: 8px;
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(8, 8, 8, 8)
        self._btns = []
        for i, item in enumerate(self._items):
            from PyQt6.QtWidgets import QPushButton
            btn = QPushButton("  " + item.label)
            btn.setMinimumHeight(50)
            btn.clicked.connect(lambda _, idx=i: self._activate(idx))
            btn.setStyleSheet(_home_menu_item_normal())
            card_layout.addWidget(btn)
            self._btns.append(btn)
        self._render_selection()

    def _render_selection(self) -> None:
        from .home_overlay import _home_menu_item_normal, _home_menu_item_selected
        for i, btn in enumerate(self._btns):
            btn.setStyleSheet(_home_menu_item_selected() if i == self._selected else _home_menu_item_normal())

    def _activate(self, idx: int) -> None:
        self._feedback.play(Cue.SELECT)
        self.hide()
        if self._on_select:
            self._on_select(self._items[idx])
        self.closed.emit()

    def show_above(self, tile) -> None:
        if tile is None:
            return
        from PyQt6.QtCore import QTimer
        from PyQt6.QtGui import QKeyEvent
        self.adjustSize()
        pos = tile.mapToGlobal(tile.rect().topLeft())
        self.move(pos.x() - 50, pos.y() - self.height() - 10)
        self.show()
        self.raise_()
        QTimer.singleShot(0, lambda: self._gamepad.push_handler(self._handle_pad))

    def _handle_pad(self, event: str) -> None:
        from domain.input.vocabulary import Event
        if event in (Event.UP, Event.LEFT):
            self._selected = (self._selected - 1) % len(self._items)
            self._render_selection()
        elif event in (Event.DOWN, Event.RIGHT):
            self._selected = (self._selected + 1) % len(self._items)
            self._render_selection()
        elif event == Event.SELECT:
            self._activate(self._selected)
        elif event == Event.CANCEL:
            self._close()

    def _close(self) -> None:
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()
        self.closed.emit()

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def cancel(self) -> None:
        self._close()

    def keyPressEvent(self, event) -> None:
        from PyQt6.QtCore import Qt
        from domain.input.vocabulary import Event
        mapped = {
            Qt.Key.Key_Up: Event.UP,
            Qt.Key.Key_Down: Event.DOWN,
            Qt.Key.Key_Return: Event.SELECT,
            Qt.Key.Key_Escape: Event.CANCEL,
        }.get(event.key())
        if mapped:
            self._handle_pad(mapped)
        super().keyPressEvent(event)