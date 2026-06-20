#!/usr/bin/env python3
"""
Windows PoC entry point for Kasual Desktop.

This demonstrates:
1. Fullscreen shell takeover (Steam Big Picture style)
2. pygame-based gamepad input (cooperative model)
3. BTN_MODE always showing HomeOverlay
4. Basic navigation with gamepad

Run with: python src/infrastructure/windows/poc_main.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  [%(name)-22s]  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    from PyQt6.QtCore import Qt, QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout

    app = QApplication(sys.argv)
    app.setApplicationName("Kasual Desktop PoC")

    class AppSignals(QObject):
        show_home = pyqtSignal()
        nav_event = pyqtSignal(str)

    signals = AppSignals()

    from infrastructure.windows.shell import WindowsShellManager
    shell = WindowsShellManager(on_exit_requested=app.quit)

    overlay_holder = {"overlay": None}

    def show_home():
        from infrastructure.windows.qt.home_overlay import HomeOverlay
        if overlay_holder["overlay"] is None:
            overlay_holder["overlay"] = HomeOverlay(
                on_select=lambda action: logger.info("Selected: %s", action),
                on_cancel=lambda: app.quit(),
            )
        overlay_holder["overlay"].show_overlay()

    signals.show_home.connect(show_home)

    shell_window = shell.install()
    shell_window._on_key_escape = lambda: signals.show_home.emit()

    from infrastructure.windows.desktop_shell import get_desktop_shell
    get_desktop_shell().set_shell_window(shell_window)

    from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
    gamepad = WindowsGamepadWatcher()

    def handle_nav(event: str):
        logger.debug("handle_nav called with: %s", event)
        signals.nav_event.emit(event)

    def _do_nav(event: str):
        logger.debug("_do_nav: event=%s", event)
        overlay = overlay_holder["overlay"]
        logger.debug("overlay=%s, visible=%s",
                     overlay is not None, overlay.isVisible() if overlay else False)
        if overlay and overlay.isVisible():
            overlay.handle_navigation(event)

    signals.nav_event.connect(_do_nav)

    gamepad.push_handler(handle_nav)
    gamepad.on_btn_mode(lambda: signals.show_home.emit())
    gamepad.on_connected(lambda e: logger.info("Gamepad connected"))
    gamepad.on_disconnected(lambda e: logger.info("Gamepad disconnected"))

    label = QLabel(
        "<h1>Kasual Desktop PoC</h1>"
        "<p>Press <b>Xbox button (BTN_MODE)</b> to open Home Overlay</p>"
        "<p>Use <b>D-pad/stick</b> to navigate, <b>A</b> to select, <b>B</b> to cancel</p>"
        "<p>Press <b>ESC</b> to show overlay</p>"
        "<hr>"
        "<p><i>Note: This is a Proof of Concept. Full implementation coming.</i></p>"
    )
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("""
        QLabel {
            color: white;
            font-size: 18px;
            padding: 40px;
            background-color: #1a1a2a;
        }
        h1 {
            color: #6ab04c;
            font-size: 36px;
        }
    """)

    btn_close = QPushButton("Zamknij aplikację")
    btn_close.setStyleSheet("""
        QPushButton {
            padding: 10px 20px;
            font-size: 14px;
            background-color: #c0392b;
            color: white;
            border: none;
            border-radius: 6px;
            min-width: 150px;
        }
        QPushButton:hover {
            background-color: #e74c3c;
        }
    """)
    btn_close.clicked.connect(app.quit)

    btn_minimize = QPushButton("Minimalizuj")
    btn_minimize.setStyleSheet("""
        QPushButton {
            padding: 10px 20px;
            font-size: 14px;
            background-color: #34495e;
            color: white;
            border: none;
            border-radius: 6px;
            min-width: 150px;
        }
        QPushButton:hover {
            background-color: #4a6278;
        }
    """)
    btn_minimize.clicked.connect(lambda: get_desktop_shell().pause())

    layout = QVBoxLayout()
    layout.addWidget(label)
    layout.addWidget(btn_close)
    layout.addWidget(btn_minimize)
    layout.addStretch()
    shell_window.setLayout(layout)

    app.aboutToQuit.connect(lambda: gamepad.shutdown())

    logger.info("Kasual Desktop PoC running - press BTN_MODE or ESC to test")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()