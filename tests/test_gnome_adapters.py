"""Tests for the GNOME adapters (window manager, surface, wallpaper).

The D-Bus helper and the OS layer are mocked: the window manager is fed canned
``ListWindows`` JSON and its ``helper.call`` is captured; the wallpaper's
``gsettings`` reads are stubbed. No GNOME Shell or session bus is contacted.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from domain.catalog.window import Window
from domain.shell.wallpaper import Wallpaper
from infrastructure.common.qt.ui.layer_shell import Anchor, Keyboard, Layer
from infrastructure.gnome.display.wallpaper import GnomeSystemWallpaper
from infrastructure.gnome.qt.surface import GnomeSurface
from infrastructure.gnome.wm.window_manager import GnomeWindowManager

_WM = "infrastructure.gnome.wm.window_manager"


# ── GnomeWindowManager ───────────────────────────────────────────────────────

def _win(id, pid, wm_class, title="", active=False, desktop_file="",
         fullscreen=False):
    return {"id": id, "pid": pid, "wm_class": wm_class, "title": title,
            "active": active, "desktop_file": desktop_file,
            "fullscreen": fullscreen}


class TestEnumWindows:
    def test_maps_and_marks_active(self, qapp):
        wm = GnomeWindowManager()
        raw = json.dumps([_win("100", 1000, "firefox", "Firefox", active=True),
                          _win("101", 2000, "mpv", "Video")])
        with patch(f"{_WM}.helper.list_windows_json", return_value=raw):
            result = wm._enum_windows()
        by_id = {w.id: w for w in result}
        assert by_id["100"].active is True and by_id["100"].resource_class == "firefox"
        assert by_id["101"].active is False and by_id["101"].pid == 2000

    def test_carries_desktop_file_and_fullscreen(self, qapp):
        """An XWayland window's wm_class ("Bitwarden") differs from the .desktop id
        the tile matches on; the extension resolves the app id so attribution works."""
        wm = GnomeWindowManager()
        raw = json.dumps([_win("1", 1000, "Bitwarden",
                               desktop_file="com.bitwarden.desktop.desktop",
                               fullscreen=True)])
        with patch(f"{_WM}.helper.list_windows_json", return_value=raw):
            w = wm._enum_windows()[0]
        assert w.desktop_file == "com.bitwarden.desktop.desktop"
        assert w.fullscreen is True

    def test_skips_classless_and_own_pid(self, qapp):
        wm = GnomeWindowManager()
        wm._our_pid = 4242
        raw = json.dumps([_win("1", 2000, ""), _win("2", 4242, "kasual-desktop")])
        with patch(f"{_WM}.helper.list_windows_json", return_value=raw):
            assert wm._enum_windows() == []

    def test_empty_on_helper_failure(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.helper.list_windows_json", return_value=None):
            assert wm._enum_windows() == []

    def test_empty_on_bad_json(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.helper.list_windows_json", return_value="not json"):
            assert wm._enum_windows() == []


class TestOps:
    def _seed(self, wm, entries):
        wm._cache = {i: Window(id=i, title="", pid=p, resource_class="x")
                     for i, p in entries}

    def test_activate_and_close(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.helper.call") as call:
            wm.activate_window("100")
            wm.close_window("100")
        call.assert_any_call("ActivateWindow", "100")
        call.assert_any_call("CloseWindow", "100")

    def test_minimize_expands_pids_and_passes_json(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.expand_pid_tree", return_value={1000, 1001}), \
             patch(f"{_WM}.helper.call") as call:
            wm.minimize_windows_for_pids({1000})
        call.assert_called_once_with("MinimizeWindowsForPids", json.dumps([1000, 1001]))

    def test_minimize_noop_when_no_pids(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.expand_pid_tree", return_value=set()), \
             patch(f"{_WM}.helper.call") as call:
            wm.minimize_windows_for_pids(set())
        call.assert_not_called()

    def test_activate_for_pids_matches_expanded(self, qapp):
        wm = GnomeWindowManager()
        self._seed(wm, [("100", 1000), ("101", 2000)])
        with patch(f"{_WM}.expand_pid_tree", return_value={1000}), \
             patch(f"{_WM}.helper.call") as call:
            wm.activate_windows_for_pids({1000})
        call.assert_called_once_with("ActivateWindow", "100")

    def _fire_readback(self):
        """Run the focus read-back at once instead of after its 400 ms."""
        timer = patch(f"{_WM}.QTimer").start()
        timer.singleShot.side_effect = lambda _ms, callback: callback()
        return timer

    def test_an_ignored_activation_is_asked_again(self, qapp):
        """Mutter may refuse an activation without saying so; Kasual would then read its
        foreground off whatever window does hold the focus."""
        wm = GnomeWindowManager()
        self._seed(wm, [("100", 1000)])
        still_unfocused = [Window(id="100", title="", pid=1000, resource_class="x")]
        self._fire_readback()
        with patch(f"{_WM}.expand_pid_tree", return_value={1000}), \
             patch.object(GnomeWindowManager, "_enum_windows",
                          return_value=still_unfocused), \
             patch(f"{_WM}.helper.call") as call:
            wm.activate_windows_for_pids({1000})
        assert [c.args for c in call.call_args_list] == [("ActivateWindow", "100")] * 2
        patch.stopall()

    def test_an_activation_that_took_is_left_alone(self, qapp):
        wm = GnomeWindowManager()
        self._seed(wm, [("100", 1000)])
        focused = [Window(id="100", title="", pid=1000, resource_class="x", active=True)]
        self._fire_readback()
        with patch(f"{_WM}.expand_pid_tree", return_value={1000}), \
             patch.object(GnomeWindowManager, "_enum_windows", return_value=focused), \
             patch(f"{_WM}.helper.call") as call:
            wm.activate_windows_for_pids({1000})
        call.assert_called_once_with("ActivateWindow", "100")
        patch.stopall()

    def test_raise_for_pid_exact_no_expansion(self, qapp):
        wm = GnomeWindowManager()
        self._seed(wm, [("100", 1000), ("101", 1000), ("102", 2000)])
        with patch(f"{_WM}.helper.call") as call:
            wm.raise_windows_for_pid_exact(1000)
        activated = {c.args[1] for c in call.call_args_list}
        assert activated == {"100", "101"}

    def test_raise_self_is_noop(self, qapp):
        wm = GnomeWindowManager()
        with patch(f"{_WM}.helper.call") as call:
            wm.raise_self()
        call.assert_not_called()


class TestBaseMachinery:
    def test_do_refresh_updates_cache_and_emits(self, qapp):
        wm = GnomeWindowManager()
        received = []
        wm.on_windows_updated(received.append)
        wins = [Window(id="1", title="A", pid=100, active=True, resource_class="a")]
        with patch.object(wm, "_enum_windows", return_value=wins):
            wm._do_refresh()
        assert wm.get_active_window_id() == "1"
        assert wm.get_cached_title("1") == "A"
        assert wm.window_exists("1") and not wm.window_exists("2")
        assert received == [wins]

    def test_refresh_dedup(self, qapp):
        wm = GnomeWindowManager()
        wm._refresh_pending = True
        with patch(f"{_WM}.QTimer") as qtimer:
            wm._request_list_refresh()
        qtimer.singleShot.assert_not_called()

    def test_close_stops_refresh(self, qapp):
        wm = GnomeWindowManager()
        with patch.object(wm, "stop_refresh") as stop:
            wm.close()
        stop.assert_called_once()


# ── GnomeSurface ─────────────────────────────────────────────────────────────

class TestGnomeSurface:
    def test_install_registers_desktop_below_the_overlays(self):
        widget = MagicMock()
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role") as role:
            GnomeSurface().install(widget)
        widget.setWindowTitle.assert_called_once_with("Kasual Desktop")
        title, layer, anchors, keyboard = role.call_args.args
        assert title == "Kasual Desktop"
        assert layer == Layer.TOP < Layer.OVERLAY
        assert anchors == Anchor.ALL
        assert keyboard != Keyboard.NONE   # the one surface of ours that is focused

    def test_show_fullscreen_asks_for_the_screen_before_mapping(self, qapp):
        """The pin must precede the map: Mutter scans a fullscreen window straight
        out as it maps, and then composites nothing else."""
        surface = GnomeSurface()
        widget = MagicMock()
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        order = MagicMock()
        widget.showFullScreen.side_effect = lambda: order.mapped()
        with patch("infrastructure.gnome.qt.surface.helper.show_overlay",
                   side_effect=lambda: order.pinned()), \
             patch("infrastructure.gnome.qt.surface.helper.activate_surface") as focus:
            surface.show_fullscreen()
        assert [c[0] for c in order.method_calls] == ["pinned", "mapped"]
        focus.assert_called_once_with("Kasual Desktop")

    def test_activate_focuses_the_desktop_surface(self):
        surface = GnomeSurface()
        widget = MagicMock()
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        with patch("infrastructure.gnome.qt.surface.helper.activate_surface") as focus:
            surface.activate()
        widget.activateWindow.assert_called_once()
        focus.assert_called_once_with("Kasual Desktop")

    def test_hide_unmaps_widget_before_releasing_pin(self):
        surface = GnomeSurface()
        widget = MagicMock()
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        order = MagicMock()
        widget.hide.side_effect = lambda: order.widget_hidden()
        with patch("infrastructure.gnome.qt.surface.helper.hide_overlay",
                   side_effect=lambda: order.pin_released()):
            surface.hide()
        assert [c[0] for c in order.method_calls] == ["widget_hidden", "pin_released"]

    def test_drop_below_cedes_without_unmapping(self):
        """Ceding keeps the window mapped so closing the app reveals it with no
        remap; it only tells the extension to stop pinning it over the app."""
        surface = GnomeSurface()
        widget = MagicMock()
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        with patch("infrastructure.gnome.qt.surface.helper.cede_overlay") as cede, \
             patch("infrastructure.gnome.qt.surface.helper.hide_overlay") as unpin:
            surface.drop_below()
        cede.assert_called_once()
        unpin.assert_not_called()
        widget.hide.assert_not_called()

    def test_is_visible_is_logical_not_mapped_state(self, qapp):
        """After ceding, the widget stays mapped but the Desktop is not in front."""
        surface = GnomeSurface()
        widget = MagicMock()
        widget.isVisible.return_value = True
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        for fn in ("show_overlay", "activate_surface", "cede_overlay"):
            patch(f"infrastructure.gnome.qt.surface.helper.{fn}").start()
        surface.show_fullscreen()
        assert surface.is_visible() is True
        surface.drop_below()
        assert surface.is_visible() is False   # mapped, but not in front
        patch.stopall()

    def test_is_sunk_is_the_extension_s_answer(self, qapp):
        """The extension decides this from the focus, so a ceded Desktop has to ask it —
        while one in front answers without asking."""
        surface = GnomeSurface()
        widget = MagicMock()
        widget.isVisible.return_value = True
        with patch("infrastructure.gnome.qt.surface.helper.set_surface_role"):
            surface.install(widget)
        for fn in ("show_overlay", "activate_surface", "cede_overlay"):
            patch(f"infrastructure.gnome.qt.surface.helper.{fn}").start()

        with patch("infrastructure.gnome.qt.surface.helper.is_sunk") as asked:
            surface.show_fullscreen()
            assert surface.is_sunk() is False
            asked.assert_not_called()

            surface.drop_below()
            asked.return_value = True
            assert surface.is_sunk() is True
            asked.return_value = False
            assert surface.is_sunk() is False
        patch.stopall()


# ── GnomeSystemWallpaper ─────────────────────────────────────────────────────

class TestGnomeWallpaper:
    def _gsettings(self, values):
        def run(args, **kwargs):
            _, _, schema, key = args
            result = MagicMock()
            result.stdout = values.get((schema, key), "''")
            return result
        return run

    def test_reads_picture_uri(self, tmp_path):
        img = tmp_path / "w.png"
        img.write_bytes(b"x")
        values = {
            ("org.gnome.desktop.interface", "color-scheme"): "'default'",
            ("org.gnome.desktop.background", "picture-uri"): f"'file://{img}'",
        }
        with patch("infrastructure.gnome.display.wallpaper.subprocess.run",
                   side_effect=self._gsettings(values)):
            assert GnomeSystemWallpaper().current() == Wallpaper(image_path=str(img))

    def test_uses_dark_variant_when_prefer_dark(self, tmp_path):
        dark = tmp_path / "dark.png"
        dark.write_bytes(b"x")
        values = {
            ("org.gnome.desktop.interface", "color-scheme"): "'prefer-dark'",
            ("org.gnome.desktop.background", "picture-uri-dark"): f"'file://{dark}'",
        }
        with patch("infrastructure.gnome.display.wallpaper.subprocess.run",
                   side_effect=self._gsettings(values)):
            assert GnomeSystemWallpaper().current().image_path == str(dark)

    def test_none_when_unset(self):
        with patch("infrastructure.gnome.display.wallpaper.subprocess.run",
                   side_effect=self._gsettings({})):
            assert GnomeSystemWallpaper().current() is None

    def test_none_when_file_missing(self):
        values = {
            ("org.gnome.desktop.interface", "color-scheme"): "'default'",
            ("org.gnome.desktop.background", "picture-uri"): "'file:///nope/x.png'",
        }
        with patch("infrastructure.gnome.display.wallpaper.subprocess.run",
                   side_effect=self._gsettings(values)):
            assert GnomeSystemWallpaper().current() is None

    def test_none_on_gsettings_error(self):
        with patch("infrastructure.gnome.display.wallpaper.subprocess.run",
                   side_effect=FileNotFoundError):
            assert GnomeSystemWallpaper().current() is None
