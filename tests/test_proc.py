"""Tests for infrastructure.linux.proc — game detection functions.

These tests are pure: descends_from_launcher receives injected callables
instead of real /proc reads; uses_graphics_api has open() mocked out.
"""

from unittest.mock import mock_open, patch

from infrastructure.linux.proc import descends_from_launcher, uses_graphics_api


class TestDescendsFromLauncher:
    def test_direct_launcher_process(self):
        names = {1000: "steam"}.get
        assert descends_from_launcher(1000, names, lambda p: None) is True

    def test_game_under_steam_reaper(self):
        # KCD.exe → wine → pressure-vessel → reaper → steam; matched at reaper.
        names = {500: "KCD.exe", 400: "wine64-preloade", 300: "reaper", 200: "steam"}.get
        parent = {500: 400, 400: 300, 300: 200, 200: 1}.get
        assert descends_from_launcher(500, names, parent) is True

    def test_wine_prefix_matches(self):
        names = {700: "wineserver"}.get
        assert descends_from_launcher(700, names, lambda p: None) is True

    def test_heroic_launched_game(self):
        names = {800: "Game", 600: "heroic"}.get
        parent = {800: 600, 600: 1}.get
        assert descends_from_launcher(800, names, parent) is True

    def test_plain_app_is_not_a_game(self):
        names = {900: "firefox", 100: "plasmashell"}.get
        parent = {900: 100, 100: 1}.get
        assert descends_from_launcher(900, names, parent) is False

    def test_unknown_name_defaults_false(self):
        assert descends_from_launcher(123, lambda p: None, lambda p: None) is False

    def test_stops_on_cycle(self):
        names = lambda p: "x"
        parent = {5: 6, 6: 5}.get
        assert descends_from_launcher(5, names, parent) is False


def _mock_maps(content: str):
    return patch("builtins.open", mock_open(read_data=content))


class TestUsesGraphicsApi:
    def test_detects_vulkan(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libvulkan.so.1\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is True

    def test_detects_libgl(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libGL.so.1\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is True

    def test_detects_dxvk(self):
        # DXVK appears in the path when games ship their own DXVK build.
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/steamapps/common/Game/dxvk-2.3.1/x64/dxgi.dll\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is True

    def test_detects_winevulkan(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/proton/files/lib64/wine/x86_64-unix/winevulkan.so\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is True

    def test_detects_vkd3d(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/proton/files/lib64/wine/x86_64-unix/vkd3d-proton.so\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is True

    def test_libegl_not_a_game(self):
        # Qt/GTK Wayland apps load libEGL but are not games.
        maps = "7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libEGL.so.1\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is False

    def test_plain_process_not_a_game(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libc.so.6\n"
        with _mock_maps(maps):
            assert uses_graphics_api(100) is False

    def test_missing_proc_returns_false(self):
        with patch("builtins.open", side_effect=OSError):
            assert uses_graphics_api(99999) is False
