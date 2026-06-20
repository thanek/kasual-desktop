"""Windows wallpaper implementation using Win32 API."""

import ctypes
import logging
import os

from domain.shell.wallpaper import SystemWallpaper, Wallpaper

logger = logging.getLogger(__name__)

SPI_GETDESKWALLPAPER = 0x0073
MAX_PATH = 260


class WindowsSystemWallpaper(SystemWallpaper):
    """Reads the current Windows desktop wallpaper using Win32 API."""

    def current(self) -> Wallpaper | None:
        try:
            user32 = ctypes.windll.user32
            buffer = ctypes.create_unicode_buffer(MAX_PATH)
            result = user32.SystemParametersInfoW(
                SPI_GETDESKWALLPAPER, MAX_PATH, buffer, 0
            )
            if result:
                path = buffer.value
                if path and os.path.exists(path):
                    logger.info("Windows wallpaper: %s", path)
                    return Wallpaper(image_path=path)
        except Exception as e:
            logger.warning("Failed to get wallpaper: %s", e)
        return None