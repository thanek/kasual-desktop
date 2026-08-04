#!/usr/bin/env python3
"""Windows entry point for Kasual Desktop.

Run with: python src/windows_main.py (the sibling of the Linux src/main.py).

Wires the *shared* Desktop widget, overlays, and `Application` controller (the
same code used on Linux) onto Windows via the `DesktopSurface` seam. Only
genuinely OS-specific adapters live under `infrastructure.windows`: the topmost
surface, window/app/gamepad managers, wallpaper, and not-yet-implemented stubs.

Default behaviour mirrors Linux: starts in the background (only the tray icon),
surfaces the Desktop when a gamepad connects, hides again when it disconnects.
"""

import logging
import os
import sys
from pathlib import Path

# No sys.path hack: like src/main.py, running ``python src/windows_main.py`` puts
# src/ on sys.path[0], so the top-level ``infrastructure``/``domain``/``application``
# imports resolve.

logger = logging.getLogger(__name__)


def main():
    from PyQt6.QtWidgets import QApplication

    from session import (
        build_controller, build_tray, defer_start,
        run_onboarding_or_start, setup_logging, wire_notification_badge,
    )

    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "kasual-desktop"
    log_file = setup_logging(log_dir)

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setQuitOnLastWindowClosed(False)

    from infrastructure.common.single_instance import SingleInstanceGuard
    guard = SingleInstanceGuard(log_file.parent)
    if not guard.try_lock():
        sys.exit(0)
    app.aboutToQuit.connect(guard.release)

    # Localization: load the system-locale .qm and route domain.shared.i18n
    # through Qt — the same call the Linux main.py makes. Done before any widget
    # is built so every string resolves translated. The in-process log viewer
    # (LogWindow) shares this QApplication, so one call covers it too (unlike
    # Linux, where the log viewer is a separate process that translates itself).
    from infrastructure.common.qt.i18n import install_translations
    install_translations(app, str(Path(__file__).parent.parent / "locale"))

    from version import get_version
    version = get_version()

    # ── OS-specific adapters ────────────────────────────────────────────────
    from infrastructure.windows.input.gamepad_watcher import WindowsGamepadWatcher
    from infrastructure.windows.wm.window_manager import WindowsWindowManager
    from infrastructure.windows.display.wallpaper import WindowsSystemWallpaper
    from infrastructure.windows.catalog.app_manager import WindowsAppManager
    from infrastructure.windows.qt.desktop_surface import WindowsDesktopSurface, TimedLaunchHide

    surface = WindowsDesktopSurface()
    gamepad = WindowsGamepadWatcher()
    wm = WindowsWindowManager()
    wallpaper = WindowsSystemWallpaper()
    process_manager = WindowsAppManager()

    # Sound cues: the shared QtMultimedia backend works as-is on Windows. Decode
    # the WAVs now (synchronously) rather than deferring via a timer — a gamepad
    # connected at launch surfaces the Desktop and plays the START cue from the
    # queued connect handler, which would otherwise beat a deferred init and drop
    # the sound ("Unknown sound or no init()"). Decoding 6 short clips is cheap.
    from infrastructure.common.audio.feedback import SoundFeedback
    feedback = SoundFeedback()
    feedback.init()

    # ── System adapters ─────────────────────────────────────────────────────
    from infrastructure.windows.power.power import WindowsPowerControl
    from infrastructure.windows.audio.volume import WindowsVolumeControl
    from infrastructure.windows.display.brightness import WindowsBrightnessControl
    from infrastructure.windows.network.network import WindowsNetworkProbe, WindowsNetworkControl
    from infrastructure.windows.catalog.app_pinning import WindowsAppPinning
    from infrastructure.windows.hud.rtss import WindowsRtssHudControl
    from infrastructure.windows.hud.rtss_shmem import RtssAppProbe
    from infrastructure.windows.proc import parent_pid
    from infrastructure.common.qt.scheduler import QtScheduler
    from domain.notifications.center import NotificationCenter

    power = WindowsPowerControl()
    # Shared instances: the Home Overlay's Quick-adjust sliders and the top bar
    # read the same volume/brightness controls and power-default preference.
    volume = WindowsVolumeControl()
    brightness = WindowsBrightnessControl()
    from infrastructure.common.catalog.preferences import DesktopPowerPreference
    power_preference = DesktopPowerPreference()

    # ── Catalog ─────────────────────────────────────────────────────────────
    # The same freedesktop .desktop store as Linux (app_config is pure Python;
    # only config_root() differs — %APPDATA% on Windows). The catalog, tile order
    # and colours persist across restarts. (Path is imported at module scope.)
    from domain.provisioning.provisioning import Provisioning as ProvisioningUseCase
    from domain.provisioning.add_apps import AppAdder
    from infrastructure.common.catalog.app_config import (
        load_apps, DesktopAppProvisioning,
        DesktopTileOrderStore, DesktopTileSettingsStore,
    )
    from infrastructure.windows.catalog.app_discovery import WindowsAppDiscovery

    provisioning = DesktopAppProvisioning()
    provisioning_uc = ProvisioningUseCase(
        provisioning,
        WindowsAppDiscovery(),
        bundled_base=str(Path(__file__).parent.parent),
    )
    # The [＋] add-app tile reopens provisioning after first run: it offers every
    # installed app (Start Menu scan) plus the starter apps, minus the apps
    # already pinned, persisting the chosen ones through the same store as
    # onboarding.
    from infrastructure.windows.catalog.installed_apps import WindowsInstalledApps
    app_adder = AppAdder(WindowsInstalledApps(), provisioning,
                         starters=provisioning_uc.candidates)

    # ── Session (deferred behind onboarding on first run) ────────────────────
    _refs: dict = {}  # keep tray/controller/overlay alive past their scope

    def start_session() -> None:
        from infrastructure.common.qt.desktop.desktop_builder import build_desktop
        from infrastructure.windows.qt.log_window import LogWindow
        from infrastructure.windows.notifications.listener import WindowsNotificationSource

        # Recent-notifications feature (mirrors KDE): the Windows source (WinRT
        # Action-Center poller) feeds the platform-agnostic NotificationCenter,
        # which the Desktop's overlay reads. Wired here, started below.
        notification_center = NotificationCenter()
        notification_source = WindowsNotificationSource()
        notification_source.on_notification(notification_center.record)

        desktop = build_desktop(
            apps=load_apps(),
            gamepad=gamepad,
            window_manager=wm,
            wallpaper=wallpaper,
            feedback=feedback,
            volume=volume,
            brightness=brightness,
            power=power,
            scheduler=QtScheduler(),
            process_manager=process_manager,
            notifications=notification_center,
            network_control=WindowsNetworkControl(),
            order_store=DesktopTileOrderStore(),
            settings_store=DesktopTileSettingsStore(),
            app_pinning=WindowsAppPinning(),
            surface=surface,
            # Parent-PID reader for recall-trigger inheritance (a game window
            # inherits its launcher tile's BTN_MODE trigger).
            parent_of=parent_pid,
            # Game detection: ask RTSS which process it is rendering an OSD into.
            is_game_pid=RtssAppProbe().is_3d_app,
            app_adder=app_adder,
            # Protocol apps (ms-settings) have no detectable window to wait on, so
            # hide on a short timer and let the surface's foreground monitor bring
            # the Desktop back.
            deferred_hide_factory=lambda _wm, _pm, _on_cede, _on_hide:
                TimedLaunchHide(on_hide=surface.hide_for_launch),
            power_preference=power_preference,
        )

        # In-process log viewer (Windows has no layer-shell, so unlike Linux we
        # don't need a separate process — see LogWindow). Owned by start_session
        # like every other collaborator; released on quit via aboutToQuit below.
        log_window = LogWindow(log_file=str(log_file))
        tray = build_tray(
            feedback=feedback, desktop=desktop, log_viewer=log_window,
            version=version, gamepad=gamepad, quit_fn=app.quit,
            keep_alive=lambda o: _refs.__setitem__("about", o),
        )
        controller = build_controller(
            gamepad=gamepad, desktop=desktop, tray=tray, wm=wm,
            power=power, hud=WindowsRtssHudControl(),
        )
        _refs.update(desktop=desktop, tray=tray, controller=controller)

        # Subscribed after `record` above, so the count is already updated when
        # this runs; delivered on the GUI thread by the source's signal hop.
        wire_notification_badge(notification_source, desktop)
        _refs["notification_source"] = notification_source
        # Start polling only once the event loop is running, so the WinRT
        # access request / first poll never sits on the critical startup path.
        defer_start(app, notification_source)

        # Top-bar network indicator: a polling monitor over the Windows probe
        # (reuses the domain PollingNetworkMonitor), feeding the Desktop.
        from domain.network.polling import PollingNetworkMonitor
        network_monitor = PollingNetworkMonitor(WindowsNetworkProbe(), QtScheduler())
        network_monitor.on_changed(desktop.update_network_status)
        desktop.update_network_status(network_monitor.current())
        _refs["network_monitor"] = network_monitor
        defer_start(app, network_monitor)

        wm.start_periodic_refresh(3000)
        app.aboutToQuit.connect(controller.shutdown)
        app.aboutToQuit.connect(log_window.close)
        # The Desktop is NOT shown here: it starts hidden and is surfaced by the
        # Application/SessionPolicy when a gamepad connects (and re-hidden on
        # disconnect). The tray keeps the process alive meanwhile.
        logger.info("Kasual Desktop running (background; waiting for gamepad)")

    # First run: onboarding picker built from a Start Menu scan; otherwise straight
    # to the session. Mirrors the Linux composition root — uses the domain
    # Provisioning use-case (`candidates()` / `complete()`) rather than bypassing
    # it. The Windows-specific Start Menu scan lives in `WindowsAppDiscovery`.
    run_onboarding_or_start(
        provisioning, provisioning_uc, gamepad, feedback, start_session,
        keep_alive=lambda o: _refs.__setitem__("onboarding", o),
    )

    app.aboutToQuit.connect(lambda: (wm.close(), gamepad.shutdown()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
