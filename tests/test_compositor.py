"""Tests for compositor detection and the backend factory seam."""

import socket

from unittest.mock import patch

import pytest

from infrastructure.linux.compositor import (
    Compositor,
    NullWindowManager,
    build_desktop_surface,
    build_system_wallpaper,
    build_window_manager,
    detect_compositor,
)

_ENV_VARS = (
    "KDE_FULL_SESSION",
    "XDG_CURRENT_DESKTOP",
    "SWAYSOCK",
    "HYPRLAND_INSTANCE_SIGNATURE",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def live_sway_socket(clean_env, tmp_path):
    socket_path = tmp_path / "sway-ipc.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        clean_env.setenv("SWAYSOCK", str(socket_path))
        yield


@pytest.fixture
def live_hyprland_socket(clean_env, tmp_path):
    signature = "abc123"
    socket_dir = tmp_path / "hypr" / signature
    socket_dir.mkdir(parents=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_dir / ".socket.sock"))
        clean_env.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        clean_env.setenv("HYPRLAND_INSTANCE_SIGNATURE", signature)
        yield


class TestDetectCompositor:
    def test_kde_from_full_session(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        assert detect_compositor() is Compositor.KDE

    def test_kde_from_current_desktop(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "KDE")
        assert detect_compositor() is Compositor.KDE

    def test_kde_current_desktop_case_insensitive(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "plasma:kde")
        assert detect_compositor() is Compositor.KDE

    def test_gnome_from_current_desktop(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        assert detect_compositor() is Compositor.GNOME

    def test_gnome_ubuntu_variant(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
        assert detect_compositor() is Compositor.GNOME

    def test_cosmic_from_current_desktop(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        assert detect_compositor() is Compositor.COSMIC

    def test_nested_sway_under_cosmic_is_sway(self, clean_env, live_sway_socket):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        assert detect_compositor() is Compositor.SWAY

    def test_sway(self, live_sway_socket):
        assert detect_compositor() is Compositor.SWAY

    def test_hyprland(self, live_hyprland_socket):
        assert detect_compositor() is Compositor.HYPRLAND

    def test_nested_sway_under_kde_is_sway(self, clean_env, live_sway_socket):
        # A nested wlroots compositor inherits KDE_FULL_SESSION from its parent
        # session; its own socket handle is the truthful signal, so it wins.
        clean_env.setenv("KDE_FULL_SESSION", "true")
        clean_env.setenv("XDG_CURRENT_DESKTOP", "KDE")
        assert detect_compositor() is Compositor.SWAY

    def test_nested_hyprland_under_kde_is_hyprland(self, clean_env, live_hyprland_socket):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        clean_env.setenv("XDG_CURRENT_DESKTOP", "KDE")
        assert detect_compositor() is Compositor.HYPRLAND

    def test_stale_swaysock_does_not_shadow_gnome(self, clean_env, tmp_path):
        # Sway's packaging imports SWAYSOCK into the systemd user manager, which
        # outlives the session and hands the dead path to the next one.
        clean_env.setenv("SWAYSOCK", str(tmp_path / "sway-ipc.gone.sock"))
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        assert detect_compositor() is Compositor.GNOME

    def test_stale_hyprland_signature_does_not_shadow_kde(self, clean_env, tmp_path):
        clean_env.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        clean_env.setenv("HYPRLAND_INSTANCE_SIGNATURE", "long-gone")
        clean_env.setenv("KDE_FULL_SESSION", "true")
        assert detect_compositor() is Compositor.KDE

    def test_stale_swaysock_alone_is_unknown(self, clean_env, tmp_path):
        clean_env.setenv("SWAYSOCK", str(tmp_path / "sway-ipc.gone.sock"))
        assert detect_compositor() is Compositor.UNKNOWN

    def test_regular_file_at_swaysock_is_not_a_session(self, clean_env, tmp_path):
        impostor = tmp_path / "sway-ipc.sock"
        impostor.write_text("")
        clean_env.setenv("SWAYSOCK", str(impostor))
        assert detect_compositor() is Compositor.UNKNOWN

    def test_unknown_when_nothing_set(self, clean_env):
        assert detect_compositor() is Compositor.UNKNOWN


class TestFactories:
    def test_window_manager_falls_back_to_null(self, clean_env):
        assert isinstance(build_window_manager(), NullWindowManager)

    def test_window_manager_is_sway_adapter(self, live_sway_socket, qapp):
        from infrastructure.wlroots.wm.sway import SwayWindowManager
        assert isinstance(build_window_manager(), SwayWindowManager)

    def test_window_manager_is_hyprland_adapter(self, live_hyprland_socket, qapp):
        from infrastructure.wlroots.wm.hyprland import HyprlandWindowManager
        assert isinstance(build_window_manager(), HyprlandWindowManager)

    def test_wallpaper_falls_back_to_static_file(self, clean_env, tmp_path):
        clean_env.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from infrastructure.linux.display.wallpaper import StaticFileWallpaper
        wallpaper = build_system_wallpaper()
        assert isinstance(wallpaper, StaticFileWallpaper)
        assert wallpaper.current() is None   # no <config>/wallpaper present

    def test_wallpaper_is_kde_adapter_on_kde(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        from infrastructure.kde.display.wallpaper import KdeSystemWallpaper
        assert isinstance(build_system_wallpaper(), KdeSystemWallpaper)

    def test_wallpaper_is_sway_adapter(self, live_sway_socket):
        from infrastructure.wlroots.display.wallpaper import SwayWallpaper
        assert isinstance(build_system_wallpaper(), SwayWallpaper)

    def test_wallpaper_is_hyprland_adapter(self, live_hyprland_socket):
        from infrastructure.wlroots.display.wallpaper import HyprlandWallpaper
        assert isinstance(build_system_wallpaper(), HyprlandWallpaper)

    def test_wallpaper_is_gnome_adapter(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        from infrastructure.gnome.display.wallpaper import GnomeSystemWallpaper
        assert isinstance(build_system_wallpaper(), GnomeSystemWallpaper)

    def test_window_manager_is_gnome_adapter_when_helper_present(self, clean_env, qapp):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        from infrastructure.gnome.wm.window_manager import GnomeWindowManager
        with patch("infrastructure.gnome.helper.helper_present", return_value=True):
            assert isinstance(build_window_manager(), GnomeWindowManager)

    def test_window_manager_falls_back_to_null_without_helper(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        with patch("infrastructure.gnome.helper.helper_present", return_value=False):
            assert isinstance(build_window_manager(), NullWindowManager)

    def test_wallpaper_is_cosmic_adapter(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        from infrastructure.cosmic.display.wallpaper import CosmicSystemWallpaper
        assert isinstance(build_system_wallpaper(), CosmicSystemWallpaper)

    def test_window_manager_is_cosmic_adapter(self, clean_env, qapp):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        from infrastructure.cosmic.wm.window_manager import CosmicWindowManager
        with patch("infrastructure.cosmic.wm.window_manager.CosmicToplevels"), \
             patch("infrastructure.cosmic.wm.window_manager.QSocketNotifier"):
            assert isinstance(build_window_manager(), CosmicWindowManager)

    def test_window_manager_falls_back_to_null_without_the_protocols(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        from infrastructure.linux.wayland.client import WaylandError
        with patch("infrastructure.cosmic.wm.window_manager.CosmicToplevels",
                   side_effect=WaylandError("no toplevel management")):
            assert isinstance(build_window_manager(), NullWindowManager)

    def test_window_manager_falls_back_to_null_without_a_compositor(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        with patch("infrastructure.cosmic.wm.window_manager.CosmicToplevels",
                   side_effect=OSError("no such socket")):
            assert isinstance(build_window_manager(), NullWindowManager)

    def test_desktop_surface_is_layer_shell_on_cosmic(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        from infrastructure.linux.wayland.surface import LayerShellSurface
        assert isinstance(build_desktop_surface(), LayerShellSurface)

    def test_desktop_surface_is_gnome_when_helper_present(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        from infrastructure.gnome.qt.surface import GnomeSurface
        with patch("infrastructure.gnome.helper.helper_present", return_value=True):
            assert isinstance(build_desktop_surface(), GnomeSurface)

    def test_desktop_surface_is_layer_shell_on_gnome_without_helper(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        from infrastructure.linux.wayland.surface import LayerShellSurface
        with patch("infrastructure.gnome.helper.helper_present", return_value=False):
            assert isinstance(build_desktop_surface(), LayerShellSurface)

    def test_desktop_surface_is_layer_shell_on_kde(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        from infrastructure.linux.wayland.surface import LayerShellSurface
        assert isinstance(build_desktop_surface(), LayerShellSurface)


class TestSurfaceSizing:
    """Only a real wlr-layer-shell surface is sized from its anchors before it maps;
    everywhere else the widget must size itself, or it never appears at all."""

    def _sized_by_compositor(self, platform: str, layer_shell: bool = True) -> bool:
        from infrastructure.common.qt.ui import top_surface
        with patch.object(top_surface.QGuiApplication, "platformName",
                          return_value=platform), \
             patch("infrastructure.linux.wayland.layer_shell.is_available",
                   return_value=layer_shell):
            return top_surface.surface_sized_by_compositor()

    def test_layer_shell_compositor_sizes_the_surface(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        assert self._sized_by_compositor("wayland") is True

    def test_gnome_leaves_sizing_to_the_widget(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        assert self._sized_by_compositor("wayland") is False

    def test_non_wayland_leaves_sizing_to_the_widget(self, clean_env):
        assert self._sized_by_compositor("offscreen") is False

    def test_widget_sizes_itself_without_a_usable_layershellqt(self, clean_env):
        # Debian/Ubuntu/Pop!_OS ship LayerShellQt for Qt5 only. Waiting for a
        # compositor that will never size the surface leaves the Home header, the
        # hint bar and the Home Overlay invisible.
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        assert self._sized_by_compositor("wayland", layer_shell=False) is False

    def test_layer_shell_compositor_sizes_the_surface_on_cosmic(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        assert self._sized_by_compositor("wayland") is True


class TestFullscreenTranslucency:
    """An ordinary top-level asking for fullscreen may be handed to the scanout
    plane with nothing behind it, losing the dimmed backdrop's alpha; a layer-shell
    overlay is sized by its anchors and never asks."""

    def _loses_alpha(self, platform: str, layer_shell: bool = True) -> bool:
        from infrastructure.common.qt.ui import top_surface
        with patch.object(top_surface.QGuiApplication, "platformName",
                          return_value=platform), \
             patch("infrastructure.linux.wayland.layer_shell.is_available",
                   return_value=layer_shell):
            return top_surface.fullscreen_loses_translucency()

    def test_gnome_flattens_a_fullscreen_surface(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        assert self._loses_alpha("wayland") is True

    def test_layer_shell_compositors_keep_the_alpha(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        assert self._loses_alpha("wayland") is False

    def test_non_wayland_keeps_the_alpha(self, clean_env):
        assert self._loses_alpha("offscreen") is False

    def test_ordinary_window_is_used_without_a_usable_layershellqt(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "COSMIC")
        assert self._loses_alpha("wayland", layer_shell=False) is True


class TestNullWindowManager:
    def test_empty_window_list(self):
        assert NullWindowManager().cached_windows() == []

    def test_operations_are_noops(self):
        wm = NullWindowManager()
        wm.start_periodic_refresh()
        wm.activate_window("w")
        wm.minimize_windows_for_pids({1, 2})
        assert wm.get_active_window_id() is None
        assert wm.window_exists("w") is False

    def test_on_windows_updated_returns_unsubscribe(self):
        unsub = NullWindowManager().on_windows_updated(lambda _: None)
        unsub()
