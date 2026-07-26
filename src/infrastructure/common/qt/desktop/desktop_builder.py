"""Assembles the Desktop widget together with its domain coordinators.

The Desktop QWidget (see ``desktop.py``) is a pure view — it renders, handles
input edges, and implements the view/shell/control ports, but does not build
the coordinators that drive it. This builder constructs the widget, then the
coordinators (given the widget as their view/control port), then wires them
back via ``Desktop.attach`` — widget first, coordinators next, attach last, so
no delegating handler ever fires with a coordinator unset. Living in the same
package, it may reach the widget's internal collaborators without widening
its public API.
"""

from domain.catalog.app import App
from domain.catalog.app_pinner import AppPinner
from domain.catalog.catalog import AppCatalog
from domain.catalog.live_catalog import LiveCatalog
from domain.catalog.tile_settings_editor import TileSettingsEditor
from domain.input.pad_control import PadControl
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.lifecycle.cede_depth import CedeDepth
from domain.lifecycle.foreground_inspector import ForegroundInspector
from domain.lifecycle.launch_hide import LaunchHide
from domain.lifecycle.launch_show import LaunchShow
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import LocalizedPrompts
from domain.lifecycle.window_manager import WindowManager
from domain.menu.dispatcher import TileMenuDispatcher
from domain.menu.ports import AppPinning, TileSettingsStore, TileOrderStore
from domain.navigation.focus_navigator import FocusNavigator
from domain.navigation.tile_mover import TileMover
from domain.network.control import NetworkControl
from domain.notifications.center import NotificationCenter
from domain.provisioning.add_apps import AppAdder
from domain.shared.feedback import Feedback
from domain.shared.scheduler import Scheduler
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.shell.home_actions import HomeActions
from domain.shell.home_chrome import HomeChrome
from domain.shell.open_overlays import OpenOverlays
from domain.shell.wallpaper import SystemWallpaper
from domain.system.action_view import make_action_confirm
from domain.system.actions import ActionDeps
from domain.system.power_control import PowerControl
from domain.system.power_menu import PowerMenu
from domain.system.power_preference import PowerPreference
from domain.system.runner import ActionRunner
from domain.system.volume import VolumeControl
from domain.system.brightness import BrightnessControl

from collections.abc import Callable, Mapping

from .desktop import Desktop
from .dialog_host_controller import DialogHostController
from .home_surface import HomeSurface
from .power_popover_controller import PowerPopoverController
from .surface import DesktopSurface


class _ImmediateHide:
    """Fallback ``LaunchHide``: hides the Desktop immediately, no window-map wait.
    Used when no ``deferred_hide_factory`` is injected (e.g. tests), keeping
    this shared builder free of any platform import."""

    def __init__(self, on_hide: Callable[[], None]) -> None:
        self._on_hide = on_hide

    @property
    def is_armed(self) -> bool:
        return False

    def arm(self, app) -> None:
        self._on_hide()

    def cancel(self) -> None:
        pass


class _NoDeferredShow:
    """Fallback ``LaunchShow``: never returns early — the Desktop comes back when
    the app's process exits, as it did before window-driven return existed."""

    @property
    def is_armed(self) -> bool:
        return False

    @property
    def has_seen_window(self) -> bool:
        return False

    def arm(self, app) -> None:
        pass

    def cancel(self) -> None:
        pass


class _NoCedeDepth:
    """Fallback ``CedeDepth``: for surfaces whose cede is a plain unmap (Windows,
    tests), there is no ceded surface left to sink under the app's windows."""

    @property
    def is_armed(self) -> bool:
        return False

    def arm(self, app) -> None:
        pass

    def cancel(self) -> None:
        pass


def build_desktop(
    *,
    apps: AppCatalog,
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
    order_store: TileOrderStore,
    settings_store: TileSettingsStore,
    app_pinning: AppPinning,
    surface: DesktopSurface | None = None,
    deferred_hide_factory: 'Callable[[WindowManager, ProcessManager, Callable[[], None]], LaunchHide] | None' = None,
    deferred_show_factory: 'Callable[[WindowManager, ProcessManager, Callable[[], None]], LaunchShow] | None' = None,
    cede_depth_factory: 'Callable[[WindowManager, ProcessManager, Callable[[bool], None]], CedeDepth] | None' = None,
    parent_of: Callable[[int], int | None] | None = None,
    is_game_pid: Callable[[int], bool] = lambda _: False,
    app_adder: AppAdder | None = None,
    power_preference: PowerPreference | None = None,
    launch_env: 'Callable[[App], Mapping[str, str]] | None' = None,
) -> Desktop:
    """Build a fully wired Desktop: the view widget plus its domain coordinators.

    ``parent_of`` is the /proc parent-PID reader injected for recall-trigger
    inheritance (a game window inherits its launcher tile's BTN_MODE trigger).

    ``is_game_pid`` is the platform predicate that decides whether a foreground
    pid is a game (gates the in-game HUD toggle). KDE wires ``kde.proc.is_game_pid``
    (graphics-API maps check + launcher ancestry); Windows wires the RTSS signal.

    ``launch_env`` contributes extra environment per launched app (the in-game HUD
    arms a game at spawn time); the app's own ``X-Kasual-Env`` still wins over it.

    ``power_preference`` also gates the power-driven chrome: without it (bare
    test builds) no PowerMenu, Home surface or Power popover is built, and the
    BTN_MODE in-place toggle reports unhandled.
    """
    parent_of = parent_of or (lambda _pid: None)
    # Shared: the widget registers/forgets overlays; the coordinator pauses/
    # resumes the group as the surface hides and returns.
    overlays = OpenOverlays()
    # Mutable in place, so a tile reorder/recolour is seen by the lifecycle and
    # deferred hide too.
    live_apps = LiveCatalog(apps)
    widget = Desktop(
        apps=live_apps,
        gamepad=gamepad,
        window_manager=window_manager,
        wallpaper=wallpaper,
        feedback=feedback,
        process_manager=process_manager,
        notifications=notifications,
        network_control=network_control,
        overlays=overlays,
        surface=surface,
        parent_of=parent_of,
        app_adder=app_adder,
    )

    nav = FocusNavigator(
        widget._tilebar, widget._topbar,
        on_tile_menu=widget._show_tile_popover, feedback=feedback,
        gamepad=gamepad,
        hint_bar=widget._hintbar,
        on_topbar_menu=widget._show_topbar_power_menu,
    )
    # Paint the initial hints before the Desktop is ever shown, so the bar is
    # never blank on first appearance.
    nav.render()

    tile_mover = TileMover(
        view=widget._tilebar, store=order_store, gamepad=gamepad, feedback=feedback,
        hint_bar=widget._hintbar, restore_hints=nav.render,
    )

    # Hides only once the launched app's window maps. Built by a factory since it
    # needs collaborators the root can't supply directly; with none, an immediate
    # hide keeps this shared builder free of any platform import.
    if deferred_hide_factory is not None:
        deferred_hide = deferred_hide_factory(
            window_manager, process_manager,
            widget.hide_view,     # cede: stay on TOP, Keyboard.NONE
            widget.withdraw_view,  # hide: truly unmap
        )
    else:
        deferred_hide = _ImmediateHide(widget.hide_view)
    # Returns the Desktop the moment the app's last window unmaps. Its callback
    # fires long after ``lifecycle`` below is bound.
    if deferred_show_factory is not None:
        deferred_show = deferred_show_factory(
            window_manager, process_manager, lambda: lifecycle.on_app_windows_gone(),
        )
    else:
        deferred_show = _NoDeferredShow()
    # Keeps the ceded Desktop under whatever the app puts on screen — a launcher or
    # a splash would otherwise end up beneath it, unseen and unclickable.
    if cede_depth_factory is not None:
        cede_depth = cede_depth_factory(
            window_manager, process_manager, widget.sink_view,
        )
    else:
        cede_depth = _NoCedeDepth()
    # Read-only foreground/game introspection, split off the coordinator.
    inspector = ForegroundInspector(
        foreground=widget._foreground,
        window_manager=window_manager,
        apps=live_apps,
        app_manager=process_manager,
        is_game_pid=is_game_pid,
    )
    # Launch/restore/close/exit orchestration lives off the widget in a
    # testable coordinator; the Desktop is just its DesktopView.
    lifecycle = AppLifecycle(
        view=widget,
        gamepad=gamepad,
        window_manager=window_manager,
        app_manager=process_manager,
        apps=live_apps,
        foreground=widget._foreground,
        deferred_hide=deferred_hide,
        deferred_show=deferred_show,
        cede_depth=cede_depth,
        tilebar=widget._tilebar,
        pad_handler=widget._handle_pad,
        scheduler=scheduler,
        feedback=feedback,
        prompts=LocalizedPrompts(),
        inspector=inspector,
        is_paused=lambda: widget._state.paused,
        launch_env=launch_env or (lambda _app: {}),
    )
    # Coordinates show/pause/resume of the Desktop surface (the widget = view).
    desktop_coordinator = DesktopCoordinator(
        state=widget._state, view=widget, feedback=feedback, overlays=overlays,
    )
    action_runner = ActionRunner(
        ActionDeps(desktop=widget, power=power),
        make_action_confirm(widget.show_confirm),
    )

    # ``tile_menu`` and ``chrome`` are assigned further down; their lambdas only
    # run at runtime, long after attach.
    dialogs = DialogHostController(
        gamepad, feedback, overlays, widget._hintbar, nav,
        widget._surface, widget._tilebar,
        TileSettingsEditor(live_apps, settings_store), widget,
        on_tile_select=lambda item: tile_menu.dispatch(item),
        sync_hint_visibility=lambda: chrome.sync(),
    )

    power_menu = None
    home_surface = None
    power_popover = None
    if power_preference is not None:
        power_menu = PowerMenu(
            ActionDeps(desktop=widget, power=power),
            power_preference,
            make_action_confirm(widget.show_confirm),
        )
    home_actions = HomeActions(action_runner, power_menu)
    if power_menu is not None:
        home_surface = HomeSurface(
            gamepad, feedback, volume, brightness, power_menu,
            widget._home_header,
            on_action=home_actions.menu_pick,
            on_power_chooser=lambda: power_popover.open_header_chooser(),
            begin_hints=lambda: chrome.begin_overlay_hints(),
            set_hints=lambda h: chrome.set_overlay_hints(h),
            end_hints=lambda: chrome.end_overlay_hints(),
        )
        home_surface.install_surface()
        power_popover = PowerPopoverController(
            power_menu, gamepad, feedback, widget._home_header,
            home_surface, nav, widget._hintbar, overlays,
        )

    chrome = HomeChrome(
        is_desktop_visible=widget.is_visible,
        home_surface=home_surface,
        hintbar=widget._hintbar,
        header=widget._home_header,
        notifications=notifications,
        render_screen_hints=nav.render,
        dismiss_overlays=widget.dismiss_overlays,
        show_notifications_view=widget._show_notifications_view,
        power_preference=power_preference,
    )
    chrome.refresh_power_default()

    tile_menu = TileMenuDispatcher(
        dispatch_lifecycle=lifecycle.dispatch_tile_action,
        mover=tile_mover,
        pinner=AppPinner(widget._tilebar, app_pinning, feedback),
        show_settings=dialogs.show_tile_settings,
        confirm=widget.show_confirm,
        prompts=LocalizedPrompts(),
    )

    widget.attach(
        nav=nav,
        lifecycle=lifecycle,
        desktop_coordinator=desktop_coordinator,
        tile_mover=tile_mover,
        dialogs=dialogs,
        chrome=chrome,
        home_actions=home_actions,
        tile_menu=tile_menu,
        home_surface=home_surface,
        power_popover=power_popover,
    )
    return widget
