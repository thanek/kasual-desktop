"""Tests for the wlroots window managers (Sway, Hyprland) and their shared base.

The OS layer is mocked: ``_run_json`` returns canned ``swaymsg``/``hyprctl`` JSON
and ``_run`` captures the emitted CLI commands, so no compositor is contacted.
"""

import time
from unittest.mock import patch

import pytest

from domain.catalog.window import Window
from infrastructure.wlroots.wm.hyprland import HyprlandWindowManager
from infrastructure.wlroots.wm.sway import SwayWindowManager


def _con(con_id, pid, name, app_id, focused=False, x11_class=None):
    node = {
        "type": "con", "id": con_id, "pid": pid, "name": name,
        "focused": focused, "nodes": [], "floating_nodes": [],
    }
    node["app_id"] = app_id
    if x11_class is not None:
        node["window_properties"] = {"class": x11_class}
    return node


def _sway_tree(cons):
    return {
        "type": "root", "nodes": [
            {"type": "output", "nodes": [
                {"type": "workspace", "name": "1", "pid": None,
                 "nodes": cons, "floating_nodes": []},
            ], "floating_nodes": []},
        ], "floating_nodes": [],
    }


# ── Sway ─────────────────────────────────────────────────────────────────────

class TestSwayEnumWindows:
    def test_maps_view_to_window(self, qapp):
        wm = SwayWindowManager()
        tree = _sway_tree([_con(5, 1000, "Firefox", "firefox", focused=True)])
        with patch.object(wm, "_run_json", return_value=tree):
            result = wm._enum_windows()
        assert len(result) == 1
        w = result[0]
        assert (w.id, w.title, w.pid, w.active, w.resource_class) == (
            "5", "Firefox", 1000, True, "firefox")

    def test_xwayland_class_used_when_no_app_id(self, qapp):
        wm = SwayWindowManager()
        tree = _sway_tree([_con(6, 2000, "Game", None, x11_class="steam_app_1")])
        with patch.object(wm, "_run_json", return_value=tree):
            result = wm._enum_windows()
        assert result[0].resource_class == "steam_app_1"

    def test_skips_containers_without_identity(self, qapp):
        wm = SwayWindowManager()
        tree = _sway_tree([_con(7, 3000, "bare", None)])
        with patch.object(wm, "_run_json", return_value=tree):
            assert wm._enum_windows() == []

    def test_skips_own_pid(self, qapp):
        wm = SwayWindowManager()
        wm._our_pid = 4242
        tree = _sway_tree([_con(8, 4242, "Kasual", "kasual")])
        with patch.object(wm, "_run_json", return_value=tree):
            assert wm._enum_windows() == []

    def test_empty_on_query_failure(self, qapp):
        wm = SwayWindowManager()
        with patch.object(wm, "_run_json", return_value=None):
            assert wm._enum_windows() == []


class TestSwayOps:
    def _seed(self, wm, entries):
        wm._cache = {
            str(cid): Window(id=str(cid), title="", pid=pid, resource_class="x")
            for cid, pid in entries
        }

    def test_activate_and_close(self, qapp):
        wm = SwayWindowManager()
        with patch.object(wm, "_run") as run:
            wm.activate_window("5")
            wm.close_window("5")
        run.assert_any_call(["swaymsg", "[con_id=5] focus"])
        run.assert_any_call(["swaymsg", "[con_id=5] kill"])

    def test_minimize_maps_to_scratchpad_over_expanded_pids(self, qapp):
        wm = SwayWindowManager()
        self._seed(wm, [(5, 1000), (6, 1001), (7, 2000)])
        with patch("infrastructure.linux.wm.base.expand_pid_tree",
                   return_value={1000, 1001}), \
             patch.object(wm, "_run") as run:
            wm.minimize_windows_for_pids({1000})
        moved = {c.args[0][1] for c in run.call_args_list}
        assert moved == {"[con_id=5] move scratchpad", "[con_id=6] move scratchpad"}

    def test_activate_for_pids_focuses_matches(self, qapp):
        wm = SwayWindowManager()
        self._seed(wm, [(5, 1000), (7, 2000)])
        with patch("infrastructure.linux.wm.base.expand_pid_tree",
                   return_value={1000}), \
             patch.object(wm, "_run") as run:
            wm.activate_windows_for_pids({1000})
        run.assert_called_once_with(["swaymsg", "[con_id=5] focus"])

    def test_raise_for_pid_exact_no_expansion(self, qapp):
        wm = SwayWindowManager()
        self._seed(wm, [(5, 1000), (6, 1000), (7, 2000)])
        with patch.object(wm, "_run") as run:
            wm.raise_windows_for_pid_exact(1000)
        focused = {c.args[0][1] for c in run.call_args_list}
        assert focused == {"[con_id=5] focus", "[con_id=6] focus"}


class TestSwayLauncherFocusFollow:
    def _arm(self, wm, pids):
        with patch("infrastructure.linux.wm.base.expand_pid_tree", return_value=pids), \
             patch.object(wm, "_run"):
            wm.activate_windows_for_pids(pids)

    def _refresh_with(self, wm, windows):
        with patch("infrastructure.linux.wm.base.expand_pid_tree",
                   return_value={w.pid for w in windows}), \
             patch.object(wm, "_enum_windows", return_value=windows), \
             patch.object(wm, "_run") as run:
            wm._do_refresh()
        return run

    def test_focuses_launcher_mapped_behind_fullscreen(self, qapp):
        wm = SwayWindowManager()
        self._arm(wm, {1000})
        big = Window(id="5", title="Big Picture", pid=1000, active=True,
                     fullscreen=True, resource_class="steam")
        launcher = Window(id="9", title="REDlauncher", pid=1000,
                          active=False, resource_class="launcher")
        run = self._refresh_with(wm, [big, launcher])
        run.assert_called_once_with(["swaymsg", "[con_id=9] focus"])
        wm._stop_follow()

    def test_stops_once_focus_lands_inside_app(self, qapp):
        wm = SwayWindowManager()
        self._arm(wm, {1000})
        launcher = Window(id="9", title="REDlauncher", pid=1000,
                          active=True, resource_class="launcher")
        run = self._refresh_with(wm, [launcher])
        run.assert_not_called()
        assert not wm._follow_timer.isActive()

    def test_waits_while_only_fullscreen_holder_present(self, qapp):
        wm = SwayWindowManager()
        self._arm(wm, {1000})
        big = Window(id="5", title="Big Picture", pid=1000, active=True,
                     fullscreen=True, resource_class="steam")
        run = self._refresh_with(wm, [big])
        run.assert_not_called()
        assert wm._follow_timer.isActive()
        wm._stop_follow()

    def test_deadline_stops_follow(self, qapp):
        wm = SwayWindowManager()
        self._arm(wm, {1000})
        wm._follow_deadline = time.monotonic() - 1
        big = Window(id="5", title="Big Picture", pid=1000, active=True,
                     fullscreen=True, resource_class="steam")
        launcher = Window(id="9", title="REDlauncher", pid=1000,
                          active=False, resource_class="launcher")
        run = self._refresh_with(wm, [big, launcher])
        run.assert_not_called()
        assert not wm._follow_timer.isActive()


# ── Hyprland ─────────────────────────────────────────────────────────────────

def _client(address, pid, cls, title):
    return {"address": address, "pid": pid, "class": cls, "title": title}


class TestHyprlandEnumWindows:
    def test_maps_client_and_marks_active(self, qapp):
        wm = HyprlandWindowManager()
        clients = [_client("0x1", 1000, "firefox", "Firefox"),
                   _client("0x2", 2000, "mpv", "Video")]
        with patch.object(wm, "_run_json",
                          side_effect=[clients, {"address": "0x2"}]):
            result = wm._enum_windows()
        by_id = {w.id: w for w in result}
        assert by_id["0x1"].active is False
        assert by_id["0x2"].active is True
        assert by_id["0x1"].resource_class == "firefox"

    def test_skips_classless_and_own_pid(self, qapp):
        wm = HyprlandWindowManager()
        wm._our_pid = 4242
        clients = [_client("0x1", 2000, "", "noclass"),
                   _client("0x2", 4242, "kasual", "self")]
        with patch.object(wm, "_run_json", side_effect=[clients, {}]):
            assert wm._enum_windows() == []

    def test_empty_on_query_failure(self, qapp):
        wm = HyprlandWindowManager()
        with patch.object(wm, "_run_json", return_value=None):
            assert wm._enum_windows() == []


class TestHyprlandOps:
    def _seed(self, wm, entries):
        wm._cache = {
            addr: Window(id=addr, title="", pid=pid, resource_class="x")
            for addr, pid in entries
        }

    def test_activate_focuses_and_fullscreens_when_windowed(self, qapp):
        wm = HyprlandWindowManager()
        with patch.object(wm, "_run_json", return_value=[{"address": "0x1", "fullscreen": 0}]), \
             patch.object(wm, "_run") as run:
            wm.activate_window("0x1")
        run.assert_called_once_with(
            ["hyprctl", "--batch",
             "dispatch focuswindow address:0x1 ; dispatch fullscreen 0"])

    def test_activate_only_focuses_when_already_fullscreen(self, qapp):
        wm = HyprlandWindowManager()
        with patch.object(wm, "_run_json", return_value=[{"address": "0x1", "fullscreen": 2}]), \
             patch.object(wm, "_run") as run:
            wm.activate_window("0x1")
        run.assert_called_once_with(["hyprctl", "dispatch", "focuswindow", "address:0x1"])

    def test_close(self, qapp):
        wm = HyprlandWindowManager()
        with patch.object(wm, "_run") as run:
            wm.close_window("0x1")
        run.assert_called_once_with(["hyprctl", "dispatch", "closewindow", "address:0x1"])

    def test_minimize_maps_to_special_workspace(self, qapp):
        wm = HyprlandWindowManager()
        self._seed(wm, [("0x1", 1000), ("0x2", 2000)])
        with patch("infrastructure.linux.wm.base.expand_pid_tree",
                   return_value={1000}), \
             patch.object(wm, "_run") as run:
            wm.minimize_windows_for_pids({1000})
        run.assert_called_once_with(
            ["hyprctl", "dispatch", "movetoworkspacesilent",
             "special:kasual,address:0x1"])


# ── shared base machinery ────────────────────────────────────────────────────

class TestBaseMachinery:
    def test_do_refresh_updates_cache_and_emits(self, qapp):
        wm = SwayWindowManager()
        received = []
        wm.on_windows_updated(received.append)
        wins = [Window(id="1", title="A", pid=100, active=True, resource_class="a")]
        with patch.object(wm, "_enum_windows", return_value=wins):
            wm._do_refresh()
        assert wm.get_active_window_id() == "1"
        assert wm.cached_windows()[0].title == "A"
        assert wm.get_cached_title("1") == "A"
        assert wm.window_exists("1") and not wm.window_exists("2")
        assert received == [wins]

    def test_refresh_dedup(self, qapp):
        wm = SwayWindowManager()
        wm._refresh_pending = True
        with patch("infrastructure.linux.wm.base.QTimer") as qtimer:
            wm._request_list_refresh()
        qtimer.singleShot.assert_not_called()

    def test_close_stops_refresh(self, qapp):
        wm = SwayWindowManager()
        with patch.object(wm, "stop_refresh") as stop:
            wm.close()
        stop.assert_called_once()

    def test_raise_self_is_noop(self, qapp):
        wm = SwayWindowManager()
        with patch.object(wm, "_run") as run:
            wm.raise_self()
        run.assert_not_called()

    def test_run_json_degrades_to_none_on_bad_json(self, qapp):
        wm = SwayWindowManager()
        with patch("infrastructure.wlroots.wm.base.subprocess.run") as run:
            run.return_value.stdout = "not json"
            assert wm._run_json(["swaymsg", "-t", "get_tree"]) is None

    def test_run_json_degrades_to_none_on_subprocess_error(self, qapp):
        import subprocess
        wm = SwayWindowManager()
        with patch("infrastructure.wlroots.wm.base.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("swaymsg", 2.0)):
            assert wm._run_json(["swaymsg", "-t", "get_tree"]) is None
