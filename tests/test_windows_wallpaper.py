"""Tests for WindowsSystemWallpaper — reading the current desktop wallpaper.

Uses ``SystemParametersInfoW`` with ``SPI_GETDESKWALLPAPER`` to read the current
wallpaper path. All Win32 calls are mocked — no real system parameters change.

Skipped on non-Windows: ``ctypes.windll.user32`` is Windows-only.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from infrastructure.windows.wallpaper import WindowsSystemWallpaper


class TestCurrent:
    def test_returns_wallpaper_when_path_valid(self, tmp_path):
        img = tmp_path / "wallpaper.jpg"
        img.write_text("x")

        def _spi(action, buf_size, buf, flags):
            buf.value = str(img)
            return 1

        with patch("infrastructure.windows.wallpaper.ctypes.windll") as windll, \
             patch("infrastructure.windows.wallpaper.ctypes.create_unicode_buffer") as buf:
            windll.user32.SystemParametersInfoW.side_effect = _spi
            result = WindowsSystemWallpaper().current()
        assert result is not None
        assert result.image_path == str(img)

    def test_returns_none_when_api_returns_zero(self):
        with patch("infrastructure.windows.wallpaper.ctypes.windll") as windll, \
             patch("infrastructure.windows.wallpaper.ctypes.create_unicode_buffer"):
            windll.user32.SystemParametersInfoW.return_value = 0
            assert WindowsSystemWallpaper().current() is None

    def test_returns_none_when_path_empty(self):
        def _spi(action, buf_size, buf, flags):
            buf.value = ""
            return 1

        with patch("infrastructure.windows.wallpaper.ctypes.windll") as windll, \
             patch("infrastructure.windows.wallpaper.ctypes.create_unicode_buffer"):
            windll.user32.SystemParametersInfoW.side_effect = _spi
            assert WindowsSystemWallpaper().current() is None

    def test_returns_none_when_path_does_not_exist(self):
        def _spi(action, buf_size, buf, flags):
            buf.value = "C:\\does\\not\\exist.jpg"
            return 1

        with patch("infrastructure.windows.wallpaper.ctypes.windll") as windll, \
             patch("infrastructure.windows.wallpaper.ctypes.create_unicode_buffer"), \
             patch("infrastructure.windows.wallpaper.os.path.exists",
                   return_value=False):
            windll.user32.SystemParametersInfoW.side_effect = _spi
            assert WindowsSystemWallpaper().current() is None

    def test_returns_none_on_exception(self):
        with patch("infrastructure.windows.wallpaper.ctypes.windll") as windll:
            windll.user32.SystemParametersInfoW.side_effect = OSError
            assert WindowsSystemWallpaper().current() is None
