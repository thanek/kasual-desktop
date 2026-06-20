"""Builder for Windows Desktop - composes all components."""

from domain.catalog.catalog import AppCatalog
from domain.catalog.live_catalog import LiveCatalog
from domain.input.pad_control import PadControl
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.lifecycle.foreground_inspector import ForegroundInspector
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import LocalizedPrompts
from domain.lifecycle.window_manager import WindowManager
from domain.menu.ports import AppPinning, TileColorStore, TileOrderStore
from domain.navigation.focus_navigator import FocusNavigator
from domain.navigation.tile_mover import TileMover
from domain.network.control import NetworkControl
from domain.notifications.center import NotificationCenter
from domain.shared.feedback import Feedback
from domain.shared.scheduler import Scheduler
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.shell.open_overlays import OpenOverlays
from domain.shell.wallpaper import SystemWallpaper
from domain.system.action_view import make_action_confirm
from domain.system.actions import ActionDeps
from domain.system.power_control import PowerControl
from domain.system.runner import ActionRunner
from domain.system.volume import VolumeControl
from domain.system.brightness import BrightnessControl

from .desktop_view import WindowsDesktop


class _StubPowerControl:
    """Stub power control for Windows - logs actions."""

    def suspend(self) -> None:
        import logging
        logging.getLogger(__name__).info("TODO: Sleep/Suspend not implemented on Windows")

    def reboot(self) -> None:
        import logging
        logging.getLogger(__name__).info("TODO: Restart not implemented on Windows")

    def poweroff(self) -> None:
        import logging
        logging.getLogger(__name__).info("TODO: Shutdown not implemented on Windows")


class _StubVolumeControl:
    """Stub volume control for Windows - logs actions."""

    def get(self) -> float:
        return 0.5

    def set(self, value: float) -> None:
        pass


class _StubBrightnessControl:
    """Stub brightness control for Windows - logs actions."""

    def get(self) -> float:
        return 0.75

    def set(self, value: float) -> None:
        pass


class _StubNetworkControl:
    """Stub network control for Windows."""

    def connect(self, network_id: str) -> None:
        pass

    def disconnect(self) -> None:
        pass


def build_desktop(
    *,
    apps: AppCatalog,
    gamepad: PadControl,
    window_manager: WindowManager,
    wallpaper: SystemWallpaper,
    feedback: Feedback,
    volume: VolumeControl | None = None,
    brightness: BrightnessControl | None = None,
    power: PowerControl | None = None,
    scheduler: Scheduler | None = None,
    process_manager: ProcessManager | None = None,
    notifications: NotificationCenter | None = None,
    network_control: NetworkControl | None = None,
    order_store: TileOrderStore | None = None,
    color_store: TileColorStore | None = None,
    app_pinning: AppPinning | None = None,
) -> WindowsDesktop:
    """Build a fully wired Windows Desktop: the view widget plus its domain coordinators."""

    if volume is None:
        volume = _StubVolumeControl()
    if brightness is None:
        brightness = _StubBrightnessControl()
    if power is None:
        power = _StubPowerControl()
    if scheduler is None:
        from infrastructure.qt.scheduler import QtScheduler
        scheduler = QtScheduler()
    if process_manager is None:
        from infrastructure.windows.app_manager import WindowsAppManager
        process_manager = WindowsAppManager()
    if notifications is None:
        notifications = NotificationCenter()
    if network_control is None:
        network_control = _StubNetworkControl()
    if color_store is None:
        color_store = _StubTileColorStore()
    if app_pinning is None:
        app_pinning = _StubAppPinning()

    overlays = OpenOverlays()
    live_apps = LiveCatalog(apps)

    widget = WindowsDesktop(
        apps=live_apps,
        gamepad=gamepad,
        window_manager=window_manager,
        wallpaper=wallpaper,
        feedback=feedback,
        volume=volume,
        brightness=brightness,
        process_manager=process_manager,
        notifications=notifications,
        network_control=network_control,
        overlays=overlays,
        color_store=color_store,
        app_pinning=app_pinning,
    )

    nav = FocusNavigator(
        widget._tilebar, widget._topbar,
        on_tile_menu=widget._show_tile_popover,
        feedback=feedback,
        on_tile_manage=widget._show_tile_management_popover,
        gamepad=gamepad,
    )

    tile_mover = TileMover(
        view=widget._tilebar, store=order_store, gamepad=gamepad, feedback=feedback,
    )

    def _stub_parent_pid(pid: int) -> int | None:
        return None

    def _stub_process_name(pid: int) -> str | None:
        return None

    inspector = ForegroundInspector(
        foreground=widget._foreground,
        window_manager=window_manager,
        apps=live_apps,
        app_manager=process_manager,
        parent_of=_stub_parent_pid,
        process_name_of=_stub_process_name,
    )

    lifecycle = AppLifecycle(
        view=widget,
        gamepad=gamepad,
        window_manager=window_manager,
        app_manager=process_manager,
        apps=live_apps,
        foreground=widget._foreground,
        deferred_hide=_StubDeferredHide(widget, widget.hide_view),
        tilebar=widget._tilebar,
        pad_handler=widget._handle_pad,
        scheduler=scheduler,
        feedback=feedback,
        prompts=LocalizedPrompts(),
        inspector=inspector,
    )

    desktop_coordinator = DesktopCoordinator(
        state=widget._state, view=widget, feedback=feedback, overlays=overlays,
    )

    action_runner = ActionRunner(
        ActionDeps(desktop=widget, power=power),
        make_action_confirm(
            lambda q, cb: widget._show_confirm(question=q, on_confirmed=cb)
        ),
    )

    widget.attach(nav, lifecycle, desktop_coordinator, action_runner, tile_mover)
    return widget


class _StubDeferredHide:
    """Stub deferred hide for Windows - minimizes shell after short delay."""

    def __init__(self, desktop, on_hide):
        self._desktop = desktop
        self._on_hide = on_hide
        self._timer = None

    def arm(self, idx: int) -> None:
        from PyQt6.QtCore import QTimer
        self.cancel()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_hide)
        self._timer.start(500)

    def disarm(self) -> None:
        self.cancel()

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None


class _StubTileColorStore:
    """Stub tile color store."""

    def get_color(self, idx: int) -> str | None:
        return None

    def set_color(self, idx: int, color: str) -> None:
        pass


class _StubAppPinning:
    """Stub app pinning."""

    def pin(self, window) -> None:
        pass

    def unpin(self, idx: int) -> None:
        pass