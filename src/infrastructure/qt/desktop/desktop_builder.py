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
from domain.input.pad_control import PadControl
from domain.lifecycle.app_lifecycle import AppLifecycle
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.prompts import LocalizedPrompts
from domain.lifecycle.window_manager import WindowManager
from domain.navigation.focus_navigator import FocusNavigator
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

from .deferred_hide import DeferredHide
from .desktop import Desktop


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
) -> Desktop:
    """Build a fully wired Desktop: the view widget plus its domain coordinators."""
    # The open-overlay group is shared: the widget feeds it (register/forget) and
    # the coordinator pauses/resumes it as the surface hides and returns.
    overlays = OpenOverlays()
    widget = Desktop(
        apps=apps,
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
    )

    nav = FocusNavigator(
        widget._tilebar, widget._topbar,
        on_tile_menu=widget._show_tile_popover, feedback=feedback,
        gamepad=gamepad,
    )

    # The Desktop stays on screen after launching an app until that app's window
    # is actually mapped, then hides to reveal it.
    deferred_hide = DeferredHide(
        window_manager, process_manager, apps, on_hide=widget.hide,
    )
    # App launch/restore/close/exit orchestration lives off the widget in a
    # testable coordinator; the Desktop is just its DesktopView.
    lifecycle = AppLifecycle(
        view=widget,
        gamepad=gamepad,
        window_manager=window_manager,
        app_manager=process_manager,
        apps=apps,
        foreground=widget._foreground,
        deferred_hide=deferred_hide,
        tilebar=widget._tilebar,
        pad_handler=widget._handle_pad,
        scheduler=scheduler,
        feedback=feedback,
        prompts=LocalizedPrompts(),
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

    widget.attach(nav, lifecycle, desktop_coordinator, action_runner)
    return widget
