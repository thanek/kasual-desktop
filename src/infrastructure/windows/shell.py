"""
Windows shell takeover implementation.

Provides fullscreen topmost window that covers the entire desktop,
similar to Steam Big Picture mode.

Uses PyQt6 with Windows-specific flags to achieve:
- Borderless fullscreen
- Always on top (WS_EX_TOPMOST)
- No taskbar presence
- Foreground lock to prevent losing focus
"""

import logging
import os

import ctypes
from ctypes import wintypes

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
GWL_EXSTYLE = -20
HWND_TOPMOST = -1
VK_ESCAPE = 0x1B

SPI_GETDESKWALLPAPER = 0x0073
MAX_PATH = 260


class ShellWindow(QWidget):
    def __init__(self, on_key_escape=None):
        super().__init__()
        self._on_key_escape = on_key_escape

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self._on_key_escape:
                self._on_key_escape()
            event.accept()
        else:
            super().keyPressEvent(event)

    def showMinimized(self):
        super().showMinimized()


class WindowsShellManager:
    def __init__(self, on_exit_requested=None):
        self._on_exit_requested = on_exit_requested
        self._window: ShellWindow | None = None

    def install(self) -> ShellWindow:
        screen = QApplication.primaryScreen()
        if not screen:
            raise RuntimeError("No primary screen found")

        geometry = screen.geometry()
        logger.info("Creating shell window: %dx%d", geometry.width(), geometry.height())

        self._window = ShellWindow(on_key_escape=self._handle_escape)
        self._window.setWindowTitle("Kasual Desktop")
        self._window.setGeometry(geometry)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self._window.setWindowFlags(flags)

        hwnd = int(self._window.winId())
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TOPMOST)

        self._window.closeEvent = self._on_close
        self._window.showFullScreen()
        self._window.activateWindow()
        self._window.raise_()

        self._topmost_timer = QTimer()
        self._topmost_timer.timeout.connect(self._refresh_topmost)
        self._topmost_timer.start(5000)

        logger.info("Shell window installed")
        return self._window

    def _handle_escape(self):
        logger.debug("ESC pressed")

    def _refresh_topmost(self):
        if self._window and self._window.isVisible():
            hwnd = int(self._window.winId())
            user32 = ctypes.windll.user32
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE)

    def _on_close(self, event):
        if self._on_exit_requested:
            self._on_exit_requested()
        event.accept()

    def get_window(self) -> QWidget | None:
        return self._window

    def uninstall(self):
        if self._topmost_timer:
            self._topmost_timer.stop()
        if self._window:
            self._window.close()
            self._window = None


def get_windows_wallpaper() -> str | None:
    try:
        user32 = ctypes.windll.user32
        buffer = ctypes.create_unicode_buffer(MAX_PATH)
        result = user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER, MAX_PATH, buffer, 0
        )
        if result:
            path = buffer.value
            if os.path.exists(path):
                return path
    except Exception as e:
        logger.warning("Failed to get wallpaper: %s", e)
    return None