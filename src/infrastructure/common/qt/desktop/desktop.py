from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

from domain.catalog.live_catalog import LiveCatalog
from domain.shell.desktop_state import DesktopState
from domain.input.vocabulary import Event
from domain.input.pad_control import PadControl
from domain.navigation import hints as home_hints
from infrastructure.common.qt.overlays.info_dialog import InfoDialog
from infrastructure.common.qt.overlays.setup_overlay import QtSetupView
from infrastructure.common.qt.overlays.notifications_overlay import NotificationsOverlay
from infrastructure.common.qt.overlays.network_overlay import NetworkOverlay
from domain.notifications.center import NotificationCenter
from domain.network.control import NetworkControl
from domain.network.status import NetworkStatus
from domain.lifecycle.app_control import AppControl
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager
from .surface import DesktopSurface, PlainSurface
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.menu.dispatcher import TileMenuDispatcher
from domain.navigation.focus_navigator import FocusNavigator
from domain.navigation.tile_mover import TileMover
from domain.provisioning.add_apps import AppAdder
from domain.setup.gate import SetupGate
from domain.shared.feedback import Feedback
from domain.shell.desktop_view import DesktopView
from domain.shell.desktop_control import DesktopControl
from domain.shell.home_actions import HomeActions
from domain.shell.home_chrome import HomeChrome
from domain.shell.introspection import (
    HEADER, TILES, ConfirmSnapshot, FocusSnapshot, HomeMenuSnapshot, MenuItemSnapshot,
    MenuSectionSnapshot, ShellSnapshot, TileMenuSnapshot, TileSnapshot,
)
from domain.shell.open_overlays import OpenOverlays
from domain.system.desktop_shell import DesktopShell
from domain.shell.wallpaper import SystemWallpaper
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.common.qt.ui.nav_key_map import nav_key_map
from infrastructure.common.qt.ui.screen_watcher import ScreenWatcher
from .app_add_controller import AppAddController
from .dialog_host_controller import DialogHostController
from .setup_check_controller import SetupCheckController
from .hint_bar import HintBar
from .home_surface import HomeSurface
from .power_popover_controller import PowerPopoverController
from .tile_bar import TileBar
from infrastructure.common.qt.overlays.home_header import HomeHeader
from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH

# Keyboard keys → navigation events, so a keyboard drives the same handler
# stack (injected via the gamepad). The directional + confirm/dispatch core is
# shared (see nav_key_map); here we add the desktop-only shortcuts.
_KEY_MAP = {
    **nav_key_map(),
    Qt.Key.Key_Q:               Event.CLOSE,
    Qt.Key.Key_BracketLeft:    Event.SECTION_PREV,   # LB
    Qt.Key.Key_BracketRight:   Event.SECTION_NEXT,   # RB
    Qt.Key.Key_Minus:          Event.VOLUME_DOWN,    # LT
    Qt.Key.Key_Equal:          Event.VOLUME_UP,      # RT
}


class Desktop(QWidget, DesktopView, DesktopShell, DesktopControl, metaclass=ProtocolQtMeta):
    """Main environment window — always fullscreen."""

    def __init__(
        self,
        apps: LiveCatalog,
        gamepad: PadControl,
        window_manager: WindowManager,
        wallpaper: SystemWallpaper,
        feedback: Feedback,
        process_manager: ProcessManager,
        notifications: NotificationCenter,
        network_control: NetworkControl,
        overlays: OpenOverlays,
        surface: DesktopSurface | None = None,
        parent_of: 'Callable[[int], int | None] | None' = None,
        app_adder: AppAdder | None = None,
        setup_gate: SetupGate | None = None,
        setup_view: QtSetupView | None = None,
    ):
        super().__init__()
        self._apps        = apps
        self._gamepad     = gamepad
        self._wm          = window_manager
        self._system_wallpaper = wallpaper
        self._feedback    = feedback
        self._app_manager = process_manager
        self._notifications = notifications
        self._network_control = network_control
        # System-action overlays (volume/brightness/…) and the dialog/popover
        # handles (confirm, tile settings, tile popover) are tracked as a group
        # in this shared registry.
        self._overlays       = overlays
        # The add-app use-case behind the [＋] tile. Optional so offscreen test
        # builds can omit it — the [＋] tile then simply does nothing.
        self._app_adder      = app_adder
        # How this widget becomes a fullscreen, stay-on-top surface — the one
        # OS-specific seam, injected by the composition root. Falls back to a
        # plain frameless fullscreen window (offscreen tests).
        self._surface        = surface or PlainSurface()

        # Desktop visibility + paused + what the BTN_MODE menu targets (foreground).
        # The foreground is shared by reference with the AppLifecycle coordinator.
        self._state      = DesktopState()
        self._foreground = self._state.foreground

        self.setWindowTitle("Kasual Desktop")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # Establish the fullscreen, stay-on-top surface via the injected strategy.
        # On Wayland this promotes the widget to a layer-shell TOP surface (above
        # DE panels; the Home Overlay still renders above it).
        self._surface.install(self)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        # The top bar is the Home surface's collapsed header, created here (the
        # builder later builds the surface around it) and handed to the
        # FocusNavigator as the TopBarView.
        self._home_header = HomeHeader(self._open_system_action, CARD_WIDTH)
        # Mouse parity with the tile bar: hover moves the highlight, a click
        # activates the button — routed through the same navigator slots gamepad A
        # follows.
        self._home_header.button_hovered.connect(self._on_topbar_hovered)
        self._home_header.button_activated.connect(self._on_topbar_activated)
        self._home_header.button_context_menu.connect(self._on_topbar_context_menu)
        # The grab handle is visible in every context the header shows, so route it
        # through BTN_MODE (not just try_toggle_home_surface, which no-ops off the
        # Desktop) — a click then closes the on-demand overlay over an app too.
        self._home_header.toggle_requested.connect(self._gamepad.trigger_btn_mode)
        self._topbar = self._home_header
        main.addStretch(1)
        self._tilebar = TileBar(self._apps, self._app_manager, parent_of=parent_of)
        self._tilebar.tile_hovered.connect(self._on_tile_hovered)
        self._tilebar.tile_context_menu.connect(self._on_tile_context_menu)

        # Its own bottom-edge surface (not a child of this window), so it stays
        # put and only swaps content as the Home Overlay animates in/out.
        # Created before the add-app controller, which needs it.
        self._hintbar = HintBar()
        self._hintbar.install_surface()

        self._gamepad_access = SetupCheckController(
            setup_gate, setup_view, self._overlays, self._hintbar,
            restore_hints=lambda: self._nav.render() if self._nav else None,
        )

        self._app_add = AppAddController(
            self._apps, self._app_adder, self._gamepad, self._feedback,
            self._tilebar, self._overlays, self._hintbar,
            restore_hints=lambda: self._nav.render() if self._nav else None,
        )
        self._tilebar.add_requested.connect(self._app_add.show)
        main.addWidget(self._tilebar)
        main.addStretch(1)

        # Domain coordinators and dialog/popover hosts are assembled by the
        # package builder (build_desktop) and injected via attach(); the widget
        # itself stays a pure view.
        self._nav:           'FocusNavigator | None'          = None
        self._lifecycle:     'AppLifecycle | None'            = None
        self._desktop:       'DesktopCoordinator | None'      = None
        self._tile_mover:    'TileMover | None'               = None
        self._dialogs:       'DialogHostController | None'    = None
        self._chrome:        'HomeChrome | None'              = None
        self._home_actions:  'HomeActions | None'             = None
        self._tile_menu:     'TileMenuDispatcher | None'      = None
        self._home_surface:  'HomeSurface | None'             = None
        self._power_popover: 'PowerPopoverController | None'  = None

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._tilebar.refresh_status)
        self._status_timer.start(500)

        self._wallpaper: 'QPixmap | None' = self._load_wallpaper_pixmap()
        self._wallpaper_scaled: 'QPixmap | None' = None

        self._wm.on_windows_updated(self._tilebar.update_windows)

        self._screen_watcher = ScreenWatcher(self.sync_screen, parent=self)

        # Desktop is not shown at startup — build_desktop wires it via attach(),
        # then it is revealed on the connected_changed(True) signal.

    def attach(
        self,
        *,
        nav: FocusNavigator,
        lifecycle: AppLifecycle,
        desktop_coordinator: DesktopCoordinator,
        tile_mover: TileMover,
        dialogs: DialogHostController,
        chrome: HomeChrome,
        home_actions: HomeActions,
        tile_menu: TileMenuDispatcher,
        home_surface: 'HomeSurface | None' = None,
        power_popover: 'PowerPopoverController | None' = None,
    ) -> None:
        """Inject the domain coordinators assembled by build_desktop and wire the
        orchestration signals. Called once, before the Desktop is ever shown, so
        the widget's handlers — which delegate to these coordinators — never fire
        with them unset."""
        self._nav           = nav
        self._lifecycle     = lifecycle
        self._desktop       = desktop_coordinator
        self._tile_mover    = tile_mover
        self._dialogs       = dialogs
        self._chrome        = chrome
        self._home_actions  = home_actions
        self._tile_menu     = tile_menu
        self._home_surface  = home_surface
        self._power_popover = power_popover

        # Platform reactivation seam: where the surface itself detects the Desktop
        # should return (Windows polls the foreground window), route it through the
        # same idempotent domain entry point used by changeEvent on Linux.
        self._surface.on_reactivate(self._lifecycle.reactivate_desktop)

        self._tilebar.activated.connect(self._activate_tile)
        self._tilebar.windows_changed.connect(self._lifecycle.check_active_dyn_gone)
        # Not windows_changed: an app's own window is no dynamic tile, so its
        # disappearance rebuilds nothing and the deferred return would never finish.
        self._wm.on_windows_updated(lambda _w: self._lifecycle.check_pending_return())
        self._wm.on_windows_updated(lambda _w: self._lifecycle.check_awaited_launch())
        self._app_manager.on_finished(
            lambda e: self._lifecycle.on_app_finished(e.app_id))
        self._app_manager.on_launch_failed(
            lambda e: self._lifecycle.on_app_launch_failed(e.app_id, e.error))

        QApplication.instance().installEventFilter(self)

    def _activate_tile(self, target) -> None:
        # A ceded Desktop keeps its surface mapped, and once sunk under a launcher
        # it is again the topmost surface wherever that launcher doesn't reach — so
        # a stray click there must not launch anything.
        if not self._surface.is_visible():
            return
        self._lifecycle.on_tile_activated(target)

    # ── ShellIntrospection port ────────────────────────────────────────────

    def _home_menu_snapshot(self) -> HomeMenuSnapshot:
        if self._home_surface is None or not self._home_surface.is_open():
            return HomeMenuSnapshot(open=False)
        content = self._home_surface.menu_content
        return HomeMenuSnapshot(
            open=True,
            sections=tuple(
                MenuSectionSnapshot(
                    kind=str(zone.kind),
                    columns=zone.columns,
                    items=tuple(
                        MenuItemSnapshot(
                            label=item.label,
                            action=item.action,
                            focused=(zone_index == content.active
                                     and item_index == zone.index),
                        )
                        for item_index, item in enumerate(zone.items)
                    ),
                )
                for zone_index, zone in enumerate(content.zones)
            ),
        )

    def _tile_menu_snapshot(self) -> TileMenuSnapshot:
        popover = self._dialogs.active_tile_popover if self._dialogs is not None else None
        if popover is None:
            return TileMenuSnapshot(open=False)
        return TileMenuSnapshot(
            open=True,
            items=tuple(
                MenuItemSnapshot(label=item.label, action=item.action,
                                 focused=(index == popover.focused_index))
                for index, item in enumerate(popover.items)
            ),
        )

    def _confirm_snapshot(self) -> ConfirmSnapshot:
        dialog = self._dialogs.active_confirm if self._dialogs is not None else None
        if dialog is None:
            return ConfirmSnapshot(open=False)
        return ConfirmSnapshot(
            open=True,
            question=dialog.question,
            confirm_focused=dialog.confirm_focused,
        )

    def snapshot(self) -> ShellSnapshot:
        windows = self._tilebar.last_windows
        tiles = tuple(
            TileSnapshot(index=i, app_id=app.id, name=app.name,
                         running=self._tilebar.is_tile_running(i, windows))
            for i, app in enumerate(self._apps)
        )
        on_tiles = self._nav is None or self._nav.in_tiles
        index = (
            self._tilebar.current_app_index()
            if on_tiles and self._tilebar.current_is_app() else None
        )
        return ShellSnapshot(
            desktop_visible=self._surface.is_visible(),
            desktop_mapped=self.isVisible(),
            desktop_sunk=self._surface.is_sunk(),
            home_header_mapped=(
                self._home_surface is not None and self._home_surface.isVisible()
            ),
            hint_bar_mapped=self._hintbar.isVisible(),
            home_menu=self._home_menu_snapshot(),
            tile_menu=self._tile_menu_snapshot(),
            confirm=self._confirm_snapshot(),
            focus=FocusSnapshot(
                zone=TILES if on_tiles else HEADER,
                cursor=self._tilebar.cursor_index() if on_tiles else None,
                kind=self._tilebar.current_kind() if on_tiles else None,
                tile_index=index,
                app_id=tiles[index].app_id if index is not None and index < len(tiles) else None,
            ),
            tiles=tiles,
            foreground=current.name if (current := self._lifecycle.current_app()) else None,
        )

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
        self._chrome.refresh_power_default()
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
        self._dialogs.cancel()
        self._app_add.cancel()
        self._gamepad_access.cancel()
        if self._tile_mover is not None:
            self._tile_mover.cancel()

    def resume(self) -> None:
        """Restore the Desktop after reconnecting the gamepad — without resetting state."""
        self._chrome.refresh_power_default()
        self._desktop.resume()

    def withdraw(self) -> None:
        """Leave the screen when the controller goes away, chrome included."""
        self.withdraw_view()

    # ── Hint bar / Home chrome (decisions live in the HomeChrome coordinator) ─

    def begin_overlay_hints(self) -> None:
        self._chrome.begin_overlay_hints()

    def set_overlay_hints(self, hints) -> None:
        self._chrome.set_overlay_hints(hints)

    def end_overlay_hints(self) -> None:
        self._chrome.end_overlay_hints()

    # ── DesktopView port (driven by AppLifecycle) ───────────────────────────

    def is_visible(self) -> bool:
        return self._surface.is_visible()

    def show_fullscreen(self) -> None:
        self._surface.show_fullscreen()
        self._chrome.sync()
        # Coming back from drop_below() re-raises without remapping, so
        # showEvent never fires — apply its cursor guard here as well.
        self._tilebar.suppress_hover_until_move()
        QTimer.singleShot(0, self._tilebar.center_current)

    def activate(self) -> None:
        self._surface.activate()
        self._chrome.on_desktop_activated()

    def hide_view(self) -> None:
        self._surface.drop_below()
        self._chrome.sync()

    def sink_view(self, under_windows: bool) -> None:
        self._surface.sink(under_windows)

    def withdraw_view(self) -> None:
        self._surface.hide()
        self._chrome.sync()

    def take_input(self) -> None:
        self._gamepad.push_handler(self._handle_pad)

    def release_input(self) -> None:
        self._gamepad.pop_handler(self._handle_pad)

    def refresh_windows(self) -> None:
        self._wm.refresh_now()

    def close_active_dialog(self) -> None:
        self._dialogs.close_active_dialog()

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
        self._dialogs.show_confirm(question, on_confirmed, on_cancelled)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The Desktop maps under wherever the cursor was left (e.g. after an app
        # exits). Block tile hovers until the mouse actually moves, so a tile
        # under the idle cursor doesn't hijack the selection on reappearance.
        self._tilebar.suppress_hover_until_move()
        QTimer.singleShot(0, self._tilebar.center_current)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._wallpaper_scaled = None
        if hasattr(self, '_tilebar'):
            QTimer.singleShot(0, self._tilebar.center_current)

    def sync_screen(self) -> None:
        self._wallpaper_scaled = None
        self.update()
        self._tilebar.sync_screen_metrics()
        if self._home_surface is not None:
            self._home_surface.position_at_top()
        self._hintbar.position_at_bottom()

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
            if self._wallpaper_scaled is None:
                self._wallpaper_scaled = self._wallpaper.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            scaled = self._wallpaper_scaled
            x = (self.width()  - scaled.width())  // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#0b140e"))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            # KWin giving us focus back delegates the reactivate decision to the
            # domain layer; also covers launcher-forwarder apps (e.g. `steam
            # steam://...`) whose process exits before app_finished fires.
            self._lifecycle.on_focus_gained()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.isActiveWindow():
            return False
        key = event.key()
        # Escape in tiles mode with no overlay open → open Home Overlay
        # (ESCAPE_HOME); the top_handler guard restricts this to when the
        # Desktop itself owns the pad, else Escape falls through to CANCEL.
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
        if self._dialogs.tile_popover_open:
            return
        self._nav.hover_tiles()

    def _menu_owns_header(self) -> bool:
        """True while the expanded Home menu is up: the header is then its navigable
        zone 0, so header mouse events drive the menu, not the collapsed-view nav."""
        return self._home_surface is not None and self._home_surface.is_open()

    def _on_topbar_hovered(self, idx: int) -> None:
        if self._menu_owns_header():
            self._home_surface.hover_header(idx)
        else:
            self._nav.hover_topbar(idx)

    def _on_topbar_activated(self, idx: int) -> None:
        """A mouse click on a top-bar button: move focus onto it and fire it,
        matching the gamepad A path (Network/Notifications open their overlay,
        Power runs the current default). While the menu is expanded the header is
        its zone 0, so the click dispatches through the menu instead."""
        if self._menu_owns_header():
            self._home_surface.activate_header(idx)
        else:
            self._nav.hover_topbar(idx)
            self._topbar.trigger(idx)

    def _on_topbar_context_menu(self, idx: int) -> None:
        """A right-click on a top-bar button opens its dropdown — only Power has one
        (the Sleep/Restart/Shut Down chooser), matching the gamepad X path. Mirrors
        a right-click on a tile opening its popover."""
        if self._menu_owns_header():
            self._home_surface.context_header(idx)
        else:
            self._nav.hover_topbar(idx)
            self._show_topbar_power_menu(idx)

    def _on_tile_context_menu(self) -> None:
        self._nav.focus_tiles()
        self._show_tile_popover()

    def _show_tile_popover(self) -> None:
        self._dialogs.show_tile_popover()

    # ── Top bar actions ────────────────────────────────────────────────────

    def _open_system_action(self, action_type: str) -> None:
        if self._home_actions is not None:
            self._home_actions.open_header_action(action_type)

    def home_overlay_factory(self) -> 'PersistentOverlayFactory':
        """The SectionedOverlayFactory the controller uses in persistent-surface
        mode: every BTN_MODE over an app / minimized Kasual (contexts 2/3) reuses
        this one surface instead of mapping a fresh overlay.

        Fail fast without the Home surface — the factory dereferences it, and
        build_desktop only builds it when given a power preference."""
        if self._home_surface is None:
            raise RuntimeError(
                "home_overlay_factory() needs the Home surface — build_desktop() "
                "builds it only when a power_preference is provided."
            )
        from .home_surface import PersistentOverlayFactory
        return PersistentOverlayFactory(self._home_surface)

    def try_toggle_home_surface(self) -> bool:
        return self._chrome.try_toggle()

    def _show_topbar_power_menu(self, index: int) -> None:
        """Delegate the top-bar Power chooser (X / right-click on Power) to the
        collaborator. Wired as the FocusNavigator's on_topbar_menu; a no-op on
        the other header buttons and in builds without a power preference."""
        if self._power_popover is not None:
            self._power_popover.show_topbar(index)

    def refresh_notification_badge(self) -> None:
        self._chrome.refresh_notification_badge()

    def update_network_status(self, status: NetworkStatus) -> None:
        self._chrome.update_network_status(status)

    def open_network_overlay(self) -> None:
        overlay = NetworkOverlay(
            self._gamepad, self._chrome.network_status, self._network_control,
            self._feedback, parent=self, dim=False,
        )
        self._dialogs.present(overlay)
        self._hintbar.show_hints(home_hints.NETWORK)

    def open_gamepad_access_check(self) -> None:
        self._gamepad_access.show()

    def open_notifications_overlay(self) -> None:
        self._chrome.open_notifications()

    def _show_notifications_view(self) -> None:
        overlay = NotificationsOverlay(
            self._gamepad, self._notifications, self._feedback, parent=self, dim=False,
        )
        self._dialogs.present(overlay)
        self._hintbar.show_hints(home_hints.NOTIFICATIONS)
