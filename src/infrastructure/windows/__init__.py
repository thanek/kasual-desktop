"""Windows-specific infrastructure implementations for Kasual Desktop."""

from infrastructure.windows.gamepad_watcher import WindowsGamepadWatcher
from infrastructure.windows.shell import WindowsShellManager, get_windows_wallpaper
from infrastructure.windows.wallpaper import WindowsSystemWallpaper
from infrastructure.windows.window_manager import WindowsWindowManager
from infrastructure.windows.app_manager import WindowsAppManager

__all__ = [
    "WindowsGamepadWatcher",
    "WindowsShellManager",
    "get_windows_wallpaper",
    "WindowsSystemWallpaper",
    "WindowsWindowManager",
    "WindowsAppManager",
]