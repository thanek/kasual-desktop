"""Windows-specific infrastructure implementations for Kasual Desktop."""

from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
from infrastructure.windows.shell import WindowsShellManager, get_windows_wallpaper

__all__ = [
    "WindowsGamepadWatcher",
    "WindowsShellManager", 
    "get_windows_wallpaper",
]