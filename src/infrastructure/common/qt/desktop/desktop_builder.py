"""Assembles the Desktop widget together with its domain coordinators.

The Desktop QWidget is a pure view (see ``desktop.py``): it renders, handles
input edges, and implements the ``DesktopView``/``DesktopShell``/``DesktopControl``
ports — but it does not build the coordinators that drive it. This builder is the
composition seam: it constructs the widget, then the coordinators (which take the
widget as their view/control port and its child bars as their view ports), and
finally injects them back via ``Desktop.attach``.

The widget↔coordinator reference is inherently bidirectional; the builder makes it
explicit and one-directional in time — widget first, coordinators next, attach last
(before the Desktop is ever shown), so no delegating handler fires with a coordinator
unset. Living in the same package, the builder may reach the widget's internal
collaborators (``_tilebar``/``_topbar``/``_foreground``/``_state``/``_handle_pad``/
``_show_tile_popover``/``_show_confirm``) without widening the widget's public API.
"""

from domain.catalog.catalog import AppCatalog
from domain.catalog.live_catalog import LiveCatalog
from domain.input.pad_control import PadControl
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.lifecycle.foreground_inspector import ForegroundInspector
from domain.lifecycle.launch_hide import LaunchHide
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import LocalizedPrompts
from domain.lifecycle.window_manager import WindowManager
from domain.menu.ports import AppPinning, TileColorStore, TileOrderStore
from domain.navigation.focus_navigator import FocusNavigator
from domain.navigation.tile_mover import TileMover
from domain.network.control import NetworkControl
from domain.notifications.center import NotificationCenter
from domain.provisioning.add_apps import AppAdder
from domain.shared.feedback import Feedback
from domain.shared.scheduler import Scheduler
from domain.shell.desktop import Desktop as DesktopCoordinator
from domain.shell.open_overlays import OpenOverlays
from domain.shell.wallpaper import SystemWallpaper
from domain.system.action_view import make_action_confirm
from domain.system.actions import ActionDeps
from domain.system.power_control import PowerControl
from domain.system.power_preference import PowerPreference
from domain.system.runner import ActionRunner
from domain.system.volume import VolumeControl
from domain.system.brightness import BrightnessControl

from collections.abc import Callable

from .desktop import Desktop
from .surface import DesktopSurface


class _ImmediateHide:
    """Fallback ``LaunchHide``: hide the Desktop the moment an app launches, with
    no window-map wait. Used when the composition root injects no
    ``deferred_hide_factory`` — keeps the shared builder usable (e.g. in tests)
    without importing any platform's real deferred-hide."""

    def __init__(self, on_hide: Callable[[], None]) -> None:
        self._on_hide = on_hide

    @property
    def is_armed(self) -> bool:
        return False

    def arm(self, idx: int) -> None:
        self._on_hide()

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
    color_store: TileColorStore,
    app_pinning: AppPinning,
    surface: DesktopSurface | None = None,
    deferred_hide_factory: 'Callable[[WindowManager, ProcessManager, LiveCatalog, Callable[[], None]], LaunchHide] | None' = None,
    parent_of: Callable[[int], int | None] | None = None,
    is_game_pid: Callable[[int], bool] = lambda _: False,
    app_adder: AppAdder | None = None,
    power_preference: PowerPreference | None = None,
) -> Desktop:
    """Build a fully wired Desktop: the view widget plus its domain coordinators.

    ``parent_of`` is the /proc parent-PID reader injected for recall-trigger
    inheritance (a game window inherits its launcher tile's BTN_MODE trigger).

    ``is_game_pid`` is the platform predicate that decides whether a foreground
    pid is a game (gates the in-game HUD toggle). KDE wires ``kde.proc.is_game_pid``
    (graphics-API maps check + launcher ancestry); Windows wires the RTSS signal.
    """
    parent_of = parent_of or (lambda _pid: None)
    # The open-overlay group is shared: the widget feeds it (register/forget) and
    # the coordinator pauses/resumes it as the surface hides and returns.
    overlays = OpenOverlays()
    # One shared, mutable order: the tile bar reorders/recolours it in place, so
    # the lifecycle and deferred hide (which key on tile position) never drift to
    # a stale catalog and launch/close the app that used to sit at that index.
    live_apps = LiveCatalog(apps)
    widget = Desktop(
        apps=live_apps,
        gamepad=gamepad,
        window_manager=window_manager,
        wallpaper=wallpaper,
        feedback=feedback,
        volume=volume,
        brightness=brightness,
        power=power,
        scheduler=scheduler,
        process_manager=process_manager,
        notifications=notifications,
        network_control=network_control,
        overlays=overlays,
        color_store=color_store,
        app_pinning=app_pinning,
        surface=surface,
        parent_of=parent_of,
        app_adder=app_adder,
        power_preference=power_preference,
    )

    nav = FocusNavigator(
        widget._tilebar, widget._topbar,
        on_tile_menu=widget._show_tile_popover, feedback=feedback,
        gamepad=gamepad,
        hint_bar=widget._hintbar,
        on_topbar_menu=widget._show_topbar_power_menu,
    )
    # Paint the initial hints (tiles screen) before the Desktop is ever shown,
    # so the bar is never blank on first appearance.
    nav.render()

    # Move mode: slides a focused app tile past its neighbours, persisting the order.
    tile_mover = TileMover(
        view=widget._tilebar, store=order_store, gamepad=gamepad, feedback=feedback,
    )

    # The Desktop stays on screen after launching an app until that app's window
    # is actually mapped, then hides to reveal it. Hiding goes through hide_view so
    # it routes through the surface. The strategy is built by an injected factory
    # — it needs build-internal collaborators (the live catalog, the widget's
    # hide_view) the composition root can't supply directly, so the root passes a
    # factory rather than an instance. Linux builds the KWin/DBus DeferredHide;
    # Windows builds a time-based one (protocol apps like ms-settings have no
    # detectable window to wait on). With no factory we fall back to an immediate
    # hide — keeping this shared builder free of any platform import.
    if deferred_hide_factory is not None:
        deferred_hide = deferred_hide_factory(
            window_manager, process_manager, live_apps, widget.hide_view,
        )
    else:
        deferred_hide = _ImmediateHide(widget.hide_view)
    # App launch/restore/close/exit orchestration lives off the widget in a
    # testable coordinator; the Desktop is just its DesktopView.
    # Read-only foreground/game introspection, split off the coordinator.
    inspector = ForegroundInspector(
        foreground=widget._foreground,
        window_manager=window_manager,
        apps=live_apps,
        app_manager=process_manager,
        is_game_pid=is_game_pid,
    )
    lifecycle = AppLifecycle(
        view=widget,
        gamepad=gamepad,
        window_manager=window_manager,
        app_manager=process_manager,
        apps=live_apps,
        foreground=widget._foreground,
        deferred_hide=deferred_hide,
        tilebar=widget._tilebar,
        pad_handler=widget._handle_pad,
        scheduler=scheduler,
        feedback=feedback,
        prompts=LocalizedPrompts(),
        inspector=inspector,
    )
    # Coordinates show/pause/resume of the Desktop surface (the widget = view).
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
