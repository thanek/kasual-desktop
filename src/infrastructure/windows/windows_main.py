#!/usr/bin/env python3
"""
Windows entry point for Kasual Desktop.

Run with: python src/infrastructure/windows/windows_main.py
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


def main():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QVBoxLayout

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop")
    app.setQuitOnLastWindowClosed(False)

    from infrastructure.windows.shell import WindowsShellManager
    shell_manager = WindowsShellManager(on_exit_requested=app.quit)
    shell_window = shell_manager.install()

    from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
    gamepad = WindowsGamepadWatcher()

    from infrastructure.windows.window_manager import WindowsWindowManager
    wm = WindowsWindowManager()

    from infrastructure.windows.wallpaper import WindowsSystemWallpaper
    wallpaper = WindowsSystemWallpaper()

    from infrastructure.windows.app_manager import WindowsAppManager
    process_manager = WindowsAppManager()

    from infrastructure.windows.qt.desktop_builder import build_desktop
    from domain.catalog.app import App

    apps = [
        App(name="Settings", command="ms-settings:", color="#2e3440"),
        App(name="Browser", command="msedge", color="#5e81ac"),
    ]

    from domain.catalog.catalog import AppCatalog

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

    desktop = build_desktop(
        apps=catalog,
        gamepad=gamepad,
        window_manager=wm,
        wallpaper=wallpaper,
        feedback=_StubFeedback(),
        process_manager=process_manager,
    )

    desktop.set_shell_window(shell_window)

    layout = QVBoxLayout(shell_window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(desktop)

    from infrastructure.windows.desktop_shell import get_desktop_shell
    get_desktop_shell().set_shell_window(shell_window)

    def show_home_overlay():
        from infrastructure.windows.qt.home_overlay import WindowsHomeOverlayFactory
        factory = WindowsHomeOverlayFactory(gamepad, _StubFeedback())
        overlay = factory.create_home_overlay()
        overlay.show_overlay(
            on_select=lambda item: desktop._action_runner.run(item.action) if hasattr(item, 'action') and item.action else logger.info("No action for: %s", item.label),
            on_cancel=None,
        )

    gamepad.on_btn_mode(show_home_overlay)
    shell_window._on_key_escape = show_home_overlay

    def handle_nav(event: str):
        pass

    gamepad.push_handler(handle_nav)

    wm.start_periodic_refresh(3000)
    desktop.show()
    desktop.activate()

    logger.info("Kasual Desktop Windows running")

    app.aboutToQuit.connect(lambda: (wm.close(), gamepad.shutdown()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()