"""Tests for the WindowManager built on wlr-foreign-toplevel (labwc, wayfire).

The compositor stand-in drives the protocol and a fake /proc supplies the
processes, so the whole path — Wayland event to `Window` to request — runs
without a compositor.
"""

from unittest.mock import patch

import pytest

from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient
from infrastructure.linux.wayland.pid_lookup import AppIdPidResolver
from infrastructure.wlroots.wayland.foreign_toplevel import MANAGER_INTERFACE
from infrastructure.wlroots.wm.foreign_toplevel import (
    ForeignToplevelWindowManager, build,
)
from wayland_fake import FakeCompositor, pump

_MANAGER_TOPLEVEL = 0
_HANDLE_TITLE = 0
_HANDLE_APP_ID = 1
_HANDLE_STATE = 4
_HANDLE_DONE = 5
_HANDLE_CLOSED = 6

_SET_MINIMIZED = 2
_UNSET_MINIMIZED = 3
_ACTIVATE = 4
_CLOSE = 5

_STATE_ACTIVATED = 2
_STATE_FULLSCREEN = 3


@pytest.fixture
def proc(tmp_path):
    def add(pid: int, comm: str) -> None:
        directory = tmp_path / str(pid)
        directory.mkdir()
        (directory / "comm").write_text(f"{comm}\n")

    add.root = str(tmp_path)
    return add


@pytest.fixture
def compositor(monkeypatch):
    fake = FakeCompositor({"wl_seat": 5, MANAGER_INTERFACE: 3})
    fake.install(monkeypatch)
    yield fake
    fake.close()


@pytest.fixture
def wm(compositor, proc, qapp):
    manager = ForeignToplevelWindowManager(
        WaylandClient(), AppIdPidResolver(proc.root, rescan_interval_s=0))
    yield manager
    manager.close()


def open_window(compositor, handle=100, title="Firefox", app_id="firefox", states=()):
    compositor.send(compositor.bound(MANAGER_INTERFACE), _MANAGER_TOPLEVEL,
                    wire.new_id(handle))
    compositor.send(handle, _HANDLE_TITLE, wire.string(title))
    compositor.send(handle, _HANDLE_APP_ID, wire.string(app_id))
    compositor.send(handle, _HANDLE_STATE,
                    wire.array(b"".join(wire.uint(s) for s in states)))
    compositor.send(handle, _HANDLE_DONE)
    return handle


class TestEnumeration:
    def test_a_toplevel_becomes_a_window(self, wm, compositor, proc):
        proc(555, "firefox")
        open_window(compositor)
        assert pump(lambda: wm.cached_windows())

        window = wm.cached_windows()[0]
        assert (window.id, window.title, window.resource_class, window.pid) == (
            "100", "Firefox", "firefox", 555)

    def test_states_reach_the_window(self, wm, compositor):
        open_window(compositor, states=(_STATE_ACTIVATED, _STATE_FULLSCREEN))
        assert pump(lambda: wm.cached_windows())

        window = wm.cached_windows()[0]
        assert (window.active, window.fullscreen) == (True, True)
        assert wm.get_active_window_id() == "100"

    def test_a_window_with_no_matching_process_has_no_pid(self, wm, compositor):
        open_window(compositor, app_id="ghost")
        assert pump(lambda: wm.cached_windows())
        assert wm.cached_windows()[0].pid == 0

    def test_a_closed_toplevel_leaves_the_cache(self, wm, compositor):
        handle = open_window(compositor)
        assert pump(lambda: wm.cached_windows())

        compositor.send(handle, _HANDLE_CLOSED)
        assert pump(lambda: not wm.cached_windows())
        assert not wm.window_exists("100")

    def test_subscribers_hear_about_the_change(self, wm, compositor):
        seen = []
        wm.on_windows_updated(seen.append)
        open_window(compositor)
        assert pump(lambda: seen and seen[-1])


class TestOperations:
    def test_activating_a_window_restores_and_focuses_it(self, wm, compositor):
        handle = open_window(compositor)
        assert pump(lambda: wm.cached_windows())

        wm.activate_window("100")
        assert pump(lambda: len(compositor.requests_to(handle)) == 2)
        assert [r.opcode for r in compositor.requests_to(handle)] == [
            _UNSET_MINIMIZED, _ACTIVATE]

    def test_closing_a_window_asks_the_compositor(self, wm, compositor):
        handle = open_window(compositor)
        assert pump(lambda: wm.cached_windows())

        wm.close_window("100")
        assert pump(lambda: compositor.requests_to(handle))
        assert compositor.requests_to(handle)[0].opcode == _CLOSE

    def test_minimizing_by_pid_uses_the_resolved_process(self, wm, compositor, proc):
        proc(555, "firefox")
        handle = open_window(compositor)
        assert pump(lambda: any(w.pid == 555 for w in wm.cached_windows()))

        with patch("infrastructure.wlroots.wm.foreign_toplevel.expand_pid_tree",
                   return_value={555}):
            wm.minimize_windows_for_pids({555})
        assert pump(lambda: compositor.requests_to(handle))
        assert compositor.requests_to(handle)[0].opcode == _SET_MINIMIZED

    def test_a_window_with_no_pid_is_claimed_by_its_app_id(self, wm, compositor):
        handle = open_window(compositor, app_id="org.kde.kitty")
        assert pump(lambda: wm.cached_windows())

        with patch("infrastructure.wlroots.wm.foreign_toplevel.expand_pid_tree",
                   return_value={321}), \
             patch("infrastructure.wlroots.wm.foreign_toplevel.process_name",
                   return_value="kitty"):
            wm.minimize_windows_for_pids({321})
        assert pump(lambda: compositor.requests_to(handle))
        assert compositor.requests_to(handle)[0].opcode == _SET_MINIMIZED

    def test_an_unrelated_window_is_left_alone(self, wm, compositor):
        handle = open_window(compositor, app_id="firefox")
        assert pump(lambda: wm.cached_windows())

        with patch("infrastructure.wlroots.wm.foreign_toplevel.expand_pid_tree",
                   return_value={321}), \
             patch("infrastructure.wlroots.wm.foreign_toplevel.process_name",
                   return_value="kitty"):
            wm.minimize_windows_for_pids({321})
        assert not pump(lambda: compositor.requests_to(handle), timeout_s=0.2)

    def test_raising_an_exact_pid_activates_only_its_window(self, wm, compositor, proc):
        proc(555, "firefox")
        proc(666, "kitty")
        firefox = open_window(compositor, handle=100, app_id="firefox")
        kitty = open_window(compositor, handle=101, app_id="kitty")
        assert pump(lambda: len(wm.cached_windows()) == 2)

        wm.raise_windows_for_pid_exact(555)
        assert pump(lambda: compositor.requests_to(firefox))
        assert compositor.requests_to(kitty) == []


class TestBuilding:
    def test_no_backend_without_the_toplevel_manager(self, monkeypatch, qapp):
        bare = FakeCompositor({"wl_seat": 5})
        bare.install(monkeypatch)
        try:
            assert build() is None
        finally:
            bare.close()

    def test_no_backend_without_a_connection(self, monkeypatch, qapp):
        monkeypatch.delenv("WAYLAND_SOCKET", raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-absent")
        assert build() is None

    def test_the_backend_is_built_where_the_manager_exists(self, compositor, qapp):
        window_manager = build()
        try:
            assert isinstance(window_manager, ForeignToplevelWindowManager)
        finally:
            window_manager.close()
