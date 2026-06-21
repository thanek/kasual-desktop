#!/usr/bin/env python3
"""
Windows entry point for Kasual Desktop.

Run with: python src/infrastructure/windows/windows_main.py

PoC of the de-fork: this wires the *shared* Desktop widget (the same
`infrastructure.qt.desktop` UI used on Linux) onto Windows, via the
`DesktopSurface` seam. Only genuinely OS-specific adapters live under
`infrastructure.windows`: the topmost host window (surface), window/app/gamepad
managers, wallpaper, and not-yet-implemented stubs.
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


class _StubFeedback:
    """Stub feedback - no audio on Windows in Iteracja 1."""

    def play(self, cue) -> None:
        pass


class _StubHud:
    def is_available(self) -> bool: return False
    def is_enabled(self) -> bool: return False
    def enable(self) -> None: pass
    def disable(self) -> None: pass


def main():
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setQuitOnLastWindowClosed(False)

    # ── OS-specific adapters ────────────────────────────────────────────────
    from infrastructure.windows.shell import WindowsShellManager
    from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
    from infrastructure.windows.window_manager import WindowsWindowManager
    from infrastructure.windows.wallpaper import WindowsSystemWallpaper
    from infrastructure.windows.app_manager import WindowsAppManager
    from infrastructure.windows.qt.host_surface import WindowsHostSurface, TimedLaunchHide

    shell_manager = WindowsShellManager(on_exit_requested=app.quit)
    surface = WindowsHostSurface(shell_manager)            # installs the host on build
    gamepad = WindowsGamepadWatcher()
    wm = WindowsWindowManager()
    wallpaper = WindowsSystemWallpaper()
    process_manager = WindowsAppManager()

    # ── Stub adapters (Iteracja 2) ──────────────────────────────────────────
    from infrastructure.windows.stubs import (
        StubPowerControl, StubVolumeControl, StubBrightnessControl,
        StubNetworkControl, StubTileColorStore, StubAppPinning,
    )
    from infrastructure.qt.scheduler import QtScheduler
    from domain.notifications.center import NotificationCenter

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
        feedback=_StubFeedback(),
        volume=StubVolumeControl(),
        brightness=StubBrightnessControl(),
        power=StubPowerControl(),
        scheduler=QtScheduler(),
        process_manager=process_manager,
        notifications=NotificationCenter(),
        network_control=StubNetworkControl(),
        order_store=None,
        color_store=StubTileColorStore(),
        app_pinning=StubAppPinning(),
        surface=surface,
        deferred_hide=TimedLaunchHide(on_hide=surface.hide),
    )

    host = surface.host

    from infrastructure.windows.desktop_shell import get_desktop_shell
    get_desktop_shell().set_shell_window(host)

    # ── Home Overlay (BTN_MODE / ESC) ───────────────────────────────────────
    from domain.menu.entry import RETURN_TO_DESKTOP, RETURN_TO_APP, CLOSE_APP
    from domain.menu.home import compose_home_menu

    _home_overlay_ref: list = [None]

    def _dispatch_home(item):
        action = getattr(item, 'action', None)
        if action == RETURN_TO_DESKTOP:
            desktop.show_desktop()
        elif action == RETURN_TO_APP:
            desktop.app_control.restore_app(item.target)
        elif action == CLOSE_APP:
            desktop.app_control.request_close_app(item.target)
        elif action:
            desktop._action_runner.run(action)
        else:
            logger.info("No action for: %s", item.label)

    def show_home_overlay():
        from infrastructure.qt.overlays.home_overlay import HomeOverlayFactory
        overlay = _home_overlay_ref[0]
        if overlay is not None and overlay.isVisible():
            overlay.hide_overlay()
            return
        factory = HomeOverlayFactory(gamepad, _StubFeedback())
        overlay = factory.create_home_overlay()
        _home_overlay_ref[0] = overlay

        current_app = desktop.app_control.current_app() if desktop.app_control else None
        menu = compose_home_menu(foreground=current_app, hud=_StubHud(), foreground_is_game=False)
        on_cancel = (
            (lambda t=menu.cancel_restores: desktop.app_control.restore_app(t))
            if menu.cancel_restores is not None else None
        )
        overlay.show_overlay(items=menu.items, on_select=_dispatch_home, on_cancel=on_cancel)

    gamepad.on_btn_mode(show_home_overlay)
    if host is not None:
        host._on_key_escape = show_home_overlay

    desktop.take_input()

    wm.start_periodic_refresh(3000)
    desktop.show()
    desktop.activate()

    logger.info("Kasual Desktop Windows running (shared widget via surface seam)")

    app.aboutToQuit.connect(lambda: (wm.close(), gamepad.shutdown()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
