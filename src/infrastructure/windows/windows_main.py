#!/usr/bin/env python3
"""
Windows entry point for Kasual Desktop.

Run with: python src/infrastructure/windows/windows_main.py

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

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "../..")))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


class _StubHud:
    """No in-game HUD on Windows — gates the HUD toggle out of the Home Overlay."""
    def is_available(self) -> bool: return False
    def is_enabled(self) -> bool: return False
    def enable(self) -> None: pass
    def disable(self) -> None: pass


def main():
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setQuitOnLastWindowClosed(False)

    from version import get_version
    version = get_version()

    # ── OS-specific adapters ────────────────────────────────────────────────
    from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
    from infrastructure.windows.window_manager import WindowsWindowManager
    from infrastructure.windows.wallpaper import WindowsSystemWallpaper
    from infrastructure.windows.app_manager import WindowsAppManager
    from infrastructure.windows.qt.desktop_surface import WindowsDesktopSurface, TimedLaunchHide

    surface = WindowsDesktopSurface()
    gamepad = WindowsGamepadWatcher()
    wm = WindowsWindowManager()
    wallpaper = WindowsSystemWallpaper()
    process_manager = WindowsAppManager()

    # Sound cues: the shared QtMultimedia backend works as-is on Windows.
    from infrastructure.audio.feedback import SoundFeedback
    feedback = SoundFeedback()

    # ── Stub adapters (Iteracja 2) ──────────────────────────────────────────
    from infrastructure.windows.stubs import (
        StubPowerControl, StubVolumeControl, StubBrightnessControl,
        StubNetworkControl,
    )
    from infrastructure.windows.app_pinning import WindowsAppPinning
    from infrastructure.qt.scheduler import QtScheduler
    from domain.notifications.center import NotificationCenter

    power = StubPowerControl()

    # ── Catalog ─────────────────────────────────────────────────────────────
    # The same freedesktop .desktop store as Linux (app_config is pure Python;
    # only config_root() differs — %APPDATA% on Windows). The catalog, tile order
    # and colours persist across restarts.
    from domain.catalog.app import App
    from domain.provisioning.candidate import CandidateApp
    from infrastructure.system.app_config import (
        load_apps, DesktopAppProvisioning,
        DesktopTileOrderStore, DesktopTileColorStore,
    )
    from infrastructure.windows.app_discovery import discover_candidates

    provisioning = DesktopAppProvisioning()

    def _default_candidates() -> list:
        """Fallback seed when the Start Menu scan yields nothing."""
        return [
            CandidateApp(
                key="settings", order=0, default_selected=True,
                app=App(name="Settings", command="ms-settings:", color="#2e3440",
                        wm_class="SystemSettings"),
            ),
            CandidateApp(
                key="browser", order=1, default_selected=True,
                app=App(name="Browser", command="msedge", color="#5e81ac"),
            ),
        ]

    # ── Session (deferred behind onboarding on first run) ────────────────────
    _refs: dict = {}  # keep tray/controller/overlay alive past their scope

    def start_session() -> None:
        from infrastructure.qt.desktop.desktop_builder import build_desktop
        from domain.shared.feedback import Cue
        from domain.system.actions import ActionDeps
        from infrastructure.qt.ui.tray import SystemTray
        from infrastructure.qt.overlays.about_overlay import AboutOverlay
        from infrastructure.qt.overlays.home_overlay import HomeOverlayFactory
        from application import Application

        desktop = build_desktop(
            apps=load_apps(),
            gamepad=gamepad,
            window_manager=wm,
            wallpaper=wallpaper,
            feedback=feedback,
            volume=StubVolumeControl(),
            brightness=StubBrightnessControl(),
            power=power,
            scheduler=QtScheduler(),
            process_manager=process_manager,
            notifications=NotificationCenter(),
            network_control=StubNetworkControl(),
            order_store=DesktopTileOrderStore(),
            color_store=DesktopTileColorStore(),
            app_pinning=WindowsAppPinning(),
            surface=surface,
            deferred_hide=TimedLaunchHide(on_hide=surface.hide_for_launch),
        )

        tray = SystemTray(
            on_show=lambda: (feedback.play(Cue.START), desktop.show_desktop()),
            on_logs=lambda: logger.info("Log viewer not implemented on Windows yet"),
            on_about=lambda: _refs.__setitem__("about", AboutOverlay(version, gamepad, feedback)),
            on_quit=app.quit,
        )
        controller = Application(
            gamepad=gamepad,
            desktop=desktop,
            app_control=desktop.app_control,
            action_deps=ActionDeps(desktop=desktop, power=power),
            tray=tray,
            wm=wm,
            overlay_factory=HomeOverlayFactory(gamepad, feedback),
            hud=_StubHud(),
        )
        _refs.update(desktop=desktop, tray=tray, controller=controller)

        wm.start_periodic_refresh(3000)
        app.aboutToQuit.connect(controller.shutdown)
        # The Desktop is NOT shown here: it starts hidden and is surfaced by the
        # Application/SessionPolicy when a gamepad connects (and re-hidden on
        # disconnect). The tray keeps the process alive meanwhile.
        logger.info("Kasual Desktop running (background; waiting for gamepad)")

    # First run: onboarding picker built from a Start Menu scan; otherwise straight
    # to the session. Mirrors the Linux composition root.
    if not provisioning.is_provisioned():
        from infrastructure.qt.overlays.onboarding_overlay import OnboardingOverlayFactory
        candidates = discover_candidates() or _default_candidates()
        onboarding = OnboardingOverlayFactory(gamepad, feedback).create()
        _refs["onboarding"] = onboarding
        onboarding.present(
            candidates,
            on_confirm=lambda chosen: (provisioning.provision(chosen), start_session()),
        )
    else:
        start_session()

    # Decode the WAV cues once the event loop is up (mirrors Linux main.py).
    QTimer.singleShot(0, feedback.init)
    app.aboutToQuit.connect(lambda: (wm.close(), gamepad.shutdown()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
