"""Tests for the wlr-foreign-toplevel proxy, against the compositor stand-in.

The compositor's side of the protocol is spoken by hand here — the opcodes are
the same ones the proxy answers, so a mistake in either shows up as a mismatch.
"""

import struct

import pytest

from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient
from infrastructure.wlroots.wayland.foreign_toplevel import (
    MANAGER_INTERFACE, ForeignToplevelManager,
)
from wayland_fake import FakeCompositor, pump

_MANAGER_TOPLEVEL = 0
_MANAGER_FINISHED = 1
_MANAGER_STOP = 0

_HANDLE_TITLE = 0
_HANDLE_APP_ID = 1
_HANDLE_STATE = 4
_HANDLE_DONE = 5
_HANDLE_CLOSED = 6

_SET_MINIMIZED = 2
_UNSET_MINIMIZED = 3
_ACTIVATE = 4
_CLOSE = 5
_DESTROY = 7

_STATE_MINIMIZED = 1
_STATE_ACTIVATED = 2
_STATE_FULLSCREEN = 3

_FIRST_HANDLE = 100


def _states(*values: int) -> bytes:
    return wire.array(struct.pack(f"={len(values)}I", *values))


@pytest.fixture
def compositor(monkeypatch):
    fake = FakeCompositor({"wl_seat": 5, MANAGER_INTERFACE: 3})
    fake.install(monkeypatch)
    yield fake
    fake.close()


@pytest.fixture
def client(compositor, qapp):
    connection = WaylandClient()
    connection.start()
    yield connection
    connection.close()


@pytest.fixture
def manager(client, compositor):
    changes = []
    proxy = ForeignToplevelManager(client, lambda: changes.append(True))
    proxy.changes = changes
    return proxy


def _open_toplevel(compositor, manager, handle=_FIRST_HANDLE,
                   title="Firefox", app_id="firefox", states=()):
    compositor.send(compositor.bound(MANAGER_INTERFACE), _MANAGER_TOPLEVEL,
                    wire.new_id(handle))
    compositor.send(handle, _HANDLE_TITLE, wire.string(title))
    compositor.send(handle, _HANDLE_APP_ID, wire.string(app_id))
    compositor.send(handle, _HANDLE_STATE, _states(*states))
    compositor.send(handle, _HANDLE_DONE)
    assert pump(lambda: any(t.handle == handle for t in manager.snapshot()))
    return handle


class TestAvailability:
    def test_available_when_the_compositor_offers_the_manager(self, client):
        assert ForeignToplevelManager.available(client)

    def test_unavailable_without_the_global(self, monkeypatch, qapp):
        bare = FakeCompositor({"wl_seat": 5})
        bare.install(monkeypatch)
        connection = WaylandClient()
        try:
            assert not ForeignToplevelManager.available(connection)
        finally:
            connection.close()
            bare.close()


class TestSnapshot:
    def test_a_toplevel_appears_with_its_title_and_app_id(self, compositor, manager):
        _open_toplevel(compositor, manager)
        assert [(t.title, t.app_id) for t in manager.snapshot()] == [
            ("Firefox", "firefox")]

    def test_states_map_onto_flags(self, compositor, manager):
        _open_toplevel(compositor, manager,
                       states=(_STATE_ACTIVATED, _STATE_FULLSCREEN))
        toplevel = manager.snapshot()[0]
        assert (toplevel.activated, toplevel.fullscreen, toplevel.minimized) == (
            True, True, False)

    def test_nothing_is_reported_before_done(self, compositor, manager, client):
        handle = _FIRST_HANDLE
        compositor.send(compositor.bound(MANAGER_INTERFACE), _MANAGER_TOPLEVEL,
                        wire.new_id(handle))
        compositor.send(handle, _HANDLE_TITLE, wire.string("half-built"))
        pump(lambda: False, timeout_s=0.2)
        assert manager.snapshot() == []

    def test_a_later_done_updates_the_same_handle(self, compositor, manager):
        handle = _open_toplevel(compositor, manager, title="Tab one")
        compositor.send(handle, _HANDLE_TITLE, wire.string("Tab two"))
        compositor.send(handle, _HANDLE_DONE)
        assert pump(lambda: manager.snapshot()[0].title == "Tab two")
        assert len(manager.snapshot()) == 1

    def test_toplevels_keep_the_order_they_were_announced_in(self, compositor, manager):
        _open_toplevel(compositor, manager, handle=100, app_id="firefox")
        _open_toplevel(compositor, manager, handle=101, app_id="kitty")
        assert [t.app_id for t in manager.snapshot()] == ["firefox", "kitty"]

    def test_a_closed_toplevel_leaves_the_snapshot(self, compositor, manager):
        handle = _open_toplevel(compositor, manager)
        compositor.send(handle, _HANDLE_CLOSED)
        assert pump(lambda: manager.snapshot() == [])

    def test_a_closed_toplevel_is_destroyed(self, compositor, manager):
        handle = _open_toplevel(compositor, manager)
        compositor.send(handle, _HANDLE_CLOSED)
        assert pump(lambda: any(r.opcode == _DESTROY
                                for r in compositor.requests_to(handle)))

    def test_finished_empties_the_list(self, compositor, manager):
        _open_toplevel(compositor, manager)
        compositor.send(compositor.bound(MANAGER_INTERFACE), _MANAGER_FINISHED)
        assert pump(lambda: manager.snapshot() == [])

    def test_every_committed_change_is_announced(self, compositor, manager):
        handle = _open_toplevel(compositor, manager)
        compositor.send(handle, _HANDLE_CLOSED)
        assert pump(lambda: len(manager.changes) == 2)


class TestRequests:
    def test_activate_names_the_seat(self, compositor, manager, client):
        handle = _open_toplevel(compositor, manager)
        manager.activate(handle)
        client.roundtrip()
        activate = [r for r in compositor.requests_to(handle) if r.opcode == _ACTIVATE]
        assert wire.Reader(activate[0].payload).object_id() == compositor.bound("wl_seat")

    def test_minimize_and_restore(self, compositor, manager, client):
        handle = _open_toplevel(compositor, manager)
        manager.set_minimized(handle)
        manager.unset_minimized(handle)
        client.roundtrip()
        assert [r.opcode for r in compositor.requests_to(handle)] == [
            _SET_MINIMIZED, _UNSET_MINIMIZED]

    def test_close_asks_the_toplevel_to_close(self, compositor, manager, client):
        handle = _open_toplevel(compositor, manager)
        manager.close(handle)
        client.roundtrip()
        assert [r.opcode for r in compositor.requests_to(handle)] == [_CLOSE]

    def test_requests_for_an_unknown_handle_are_dropped(self, compositor, manager, client):
        manager.close(999)
        client.roundtrip()
        assert compositor.requests_to(999) == []

    def test_stop_gives_up_the_manager(self, compositor, manager, client):
        _open_toplevel(compositor, manager)
        manager.stop()
        client.roundtrip()
        stop = compositor.requests_to(compositor.bound(MANAGER_INTERFACE))
        assert [r.opcode for r in stop] == [_MANAGER_STOP]
        assert manager.snapshot() == []
