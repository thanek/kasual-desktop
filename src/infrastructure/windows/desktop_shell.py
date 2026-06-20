"""Windows shell integration for Kasual Desktop."""

import ctypes
import logging
import os
from typing import Protocol

from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class DesktopShell(Protocol):
    """The Desktop capabilities that system actions drive."""

    def open_network_overlay(self) -> None: ...
    def open_notifications_overlay(self) -> None: ...
    def open_volume_overlay(self) -> None: ...
    def open_brightness_overlay(self) -> None: ...
    def pause(self) -> None: ...
    def restore(self) -> None: ...
    def show_desktop(self) -> None: ...


class WindowsDesktopShell:
    """Windows implementation of DesktopShell protocol."""

    def __init__(self, shell_window=None):
        self._shell_window = shell_window

    def set_shell_window(self, shell_window):
        self._shell_window = shell_window

    def open_network_overlay(self) -> None:
        logger.info("Network overlay requested (not implemented in PoC)")

    def open_notifications_overlay(self) -> None:
        logger.info("Notifications overlay requested (not implemented in PoC)")

    def open_volume_overlay(self) -> None:
        logger.info("Volume overlay requested (not implemented in PoC)")

    def open_brightness_overlay(self) -> None:
        logger.info("Brightness overlay requested (not implemented in PoC)")

    def pause(self) -> None:
        """Minimize the Kasual Desktop shell (hide it)."""
        logger.info("Pause/Minimize desktop requested")
        if self._shell_window:
            self._shell_window.showMinimized()

    def restore(self) -> None:
        """Restore the Kasual Desktop window."""
        logger.info("Restore Kasual requested")
        if self._shell_window:
            self._shell_window.showFullScreen()
            self._shell_window.raise_()
            self._shell_window.activateWindow()

    def show_desktop(self) -> None:
        """Show the Windows desktop by minimizing all windows."""
        logger.info("Show desktop requested")
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(user32.GetDesktopWindow(), 6)
        except Exception as e:
            logger.warning("Failed to show desktop: %s", e)


windows_shell = WindowsDesktopShell()


def get_desktop_shell() -> WindowsDesktopShell:
    return windows_shell