"""Tests for infrastructure.linux.proc — game detection and process readings.

These tests are pure: descends_from_launcher receives injected callables
instead of real /proc reads; uses_translation_layer and process_environ have
open() mocked out.
"""

from unittest.mock import mock_open, patch

from infrastructure.linux.proc import (
    descends_from_launcher, expand_pid_tree, process_environ,
    uses_translation_layer,
)


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


class TestUsesTranslationLayer:
    def test_detects_dxvk(self):
        # DXVK appears in the path when games ship their own DXVK build.
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/steamapps/common/Game/dxvk-2.3.1/x64/dxgi.dll\n"
        with _mock_maps(maps):
            assert uses_translation_layer(100) is True

    def test_detects_winevulkan(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/proton/files/lib64/wine/x86_64-unix/winevulkan.so\n"
        with _mock_maps(maps):
            assert uses_translation_layer(100) is True

    def test_detects_vkd3d(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /home/user/.steam/proton/files/lib64/wine/x86_64-unix/vkd3d-proton.so\n"
        with _mock_maps(maps):
            assert uses_translation_layer(100) is True

    def test_vulkan_loader_alone_is_not_a_game(self):
        # A Qt video player or a Chromium-based app maps the Vulkan loader too —
        # and so does every process the MangoHud Vulkan layer attaches to.
        maps = ("7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libvulkan.so.1\n"
                "7f02-7f03 r--p 0 08:01 2 /usr/lib/x86_64-linux-gnu/libMangoHud.so\n")
        with _mock_maps(maps):
            assert uses_translation_layer(100) is False

    def test_opengl_alone_is_not_a_game(self):
        maps = ("7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libGL.so.1\n"
                "7f02-7f03 r--p 0 08:01 2 /usr/lib/x86_64-linux-gnu/libEGL.so.1\n")
        with _mock_maps(maps):
            assert uses_translation_layer(100) is False

    def test_plain_process_not_a_game(self):
        maps = "7f00-7f01 r--p 0 08:01 1 /usr/lib/x86_64-linux-gnu/libc.so.6\n"
        with _mock_maps(maps):
            assert uses_translation_layer(100) is False

    def test_missing_proc_returns_false(self):
        with patch("builtins.open", side_effect=OSError):
            assert uses_translation_layer(99999) is False


def _children_opener(children: dict[int, str]):
    """Fake ``open`` for /proc/<pid>/task/<pid>/children reads: a PID present in
    *children* yields its space-separated child list; an absent one raises (an
    already-exited process)."""
    def _open(path, *args, **kwargs):
        pid = int(path.split("/")[2])
        if pid not in children:
            raise FileNotFoundError
        return mock_open(read_data=children[pid])(path)
    return _open


class TestExpandPidTree:
    def test_single_pid_without_children(self):
        with patch("builtins.open", _children_opener({100: ""})):
            assert expand_pid_tree({100}) == {100}

    def test_expands_full_subtree(self):
        tree = {100: "101 102", 101: "103", 102: "", 103: ""}
        with patch("builtins.open", _children_opener(tree)):
            assert expand_pid_tree({100}) == {100, 101, 102, 103}

    def test_exited_child_is_skipped_not_fatal(self):
        # 100 lists child 101, but 101 has already exited (no children file).
        with patch("builtins.open", _children_opener({100: "101"})):
            assert expand_pid_tree({100}) == {100, 101}

    def test_multiple_roots_are_deduped(self):
        with patch("builtins.open", _children_opener({100: "101", 101: ""})):
            assert expand_pid_tree({100, 101}) == {100, 101}

    def test_empty_input(self):
        assert expand_pid_tree(set()) == set()


class TestProcessEnviron:
    def _reading(self, raw):
        with patch("builtins.open", mock_open(read_data=raw)):
            return process_environ(500)

    def test_parses_nul_separated_entries(self):
        assert self._reading(b"MANGOHUD=1\0PATH=/usr/bin\0") == {
            "MANGOHUD": "1", "PATH": "/usr/bin"}

    def test_keeps_values_containing_equals(self):
        assert self._reading(b"LS_COLORS=di=01;34\0") == {"LS_COLORS": "di=01;34"}

    def test_empty_for_a_process_that_is_gone(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert process_environ(500) == {}

    def test_empty_for_a_process_of_another_user(self):
        with patch("builtins.open", side_effect=PermissionError):
            assert process_environ(500) == {}
