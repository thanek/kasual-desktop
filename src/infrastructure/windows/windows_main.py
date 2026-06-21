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
        StubNetworkControl, StubTileColorStore, StubAppPinning,
    )
    from infrastructure.qt.scheduler import QtScheduler
    from domain.notifications.center import NotificationCenter

    power = StubPowerControl()

    # ── Catalog ─────────────────────────────────────────────────────────────
    from domain.catalog.app import App
    from domain.catalog.catalog import AppCatalog

    apps = [
        # wm_class matches the real hosted UWP process (SystemSettings.exe) so the
        # tile lights up as running — ms-settings: is a protocol with no launch
        # process handle, so window-matching is the only running signal.
        App(name="Settings", command="ms-settings:", color="#2e3440", wm_class="SystemSettings"),
        App(name="Browser", command="msedge", color="#5e81ac"),
    ]

    class SimpleCatalog(AppCatalog):
        def __init__(self, apps):
            self._apps = list(apps)

        def __iter__(self):
            return iter(self._apps)

        def __len__(self):
            return len(self._apps)

        def __getitem__(self, idx):
            return self._apps[idx]

        def swap(self, i, j):
            self._apps[i], self._apps[j] = self._apps[j], self._apps[i]

        def append(self, app):
            self._apps.append(app)

        def remove(self, idx):
            self._apps.pop(idx)

        def recolour(self, idx, color):
            pass

    catalog = SimpleCatalog(apps)

    # ── Build the shared Desktop with the Windows surface ────────────────────
    from infrastructure.qt.desktop.desktop_builder import build_desktop

    desktop = build_desktop(
        apps=catalog,
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
        order_store=None,
        color_store=StubTileColorStore(),
        app_pinning=StubAppPinning(),
        surface=surface,
        deferred_hide=TimedLaunchHide(on_hide=surface.hide_for_launch),
    )

    # ── Tray + Application controller (shared) ───────────────────────────────
    from domain.shared.feedback import Cue
    from domain.system.actions import ActionDeps
    from infrastructure.qt.ui.tray import SystemTray
    from infrastructure.qt.overlays.about_overlay import AboutOverlay
    from infrastructure.qt.overlays.home_overlay import HomeOverlayFactory
    from application import Application

    tray = SystemTray(
        on_show=lambda: (feedback.play(Cue.START), desktop.show_desktop()),
        on_logs=lambda: logger.info("Log viewer not implemented on Windows yet"),
        on_about=lambda: AboutOverlay(version, gamepad, feedback),
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

    wm.start_periodic_refresh(3000)
    # Decode the WAV cues once the event loop is up (mirrors Linux main.py).
    QTimer.singleShot(0, feedback.init)

    # The Desktop is NOT shown here: it starts hidden and is surfaced by the
    # Application/SessionPolicy when a gamepad connects (and re-hidden on
    # disconnect). The tray keeps the process alive meanwhile.
    logger.info("Kasual Desktop Windows running (background; waiting for gamepad)")

    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(lambda: (wm.close(), gamepad.shutdown()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
