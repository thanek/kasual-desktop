"""Tests for the COSMIC toplevel mirror, driven through a fake compositor.

The point is protocol fidelity: the opcodes are positional in the protocol XML, so
these assert the exact bytes that go out and the exact events that come back.
"""

import struct

import pytest

from infrastructure.cosmic.wm import protocol
from infrastructure.cosmic.wm.toplevels import CosmicToplevels
from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient, WaylandError
from wayland_fake import FakeCompositor, pump

_GLOBALS = {
    protocol.FOREIGN_LIST: protocol.FOREIGN_LIST_VERSION,
    protocol.INFO: protocol.INFO_VERSION,
    protocol.MANAGER: protocol.MANAGER_VERSION,
    protocol.SEAT: 9,
}

# The cosmic handles the mirror allocates, in the order it upgrades ext handles.
FIRST_HANDLE = 8

FOREIGN_A = 0xFF000000
FOREIGN_B = 0xFF000001


def _states(*values: int) -> bytes:
    return wire.array(struct.pack(f"={len(values)}I", *values))


@pytest.fixture
def compositor(monkeypatch):
    fake = FakeCompositor(dict(_GLOBALS))
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
def mirror(client, compositor):
    changes = []
    made = CosmicToplevels(client, lambda: changes.append(True))
    made.changes = changes
    # The fake reads on a thread of its own, so the binds are only assertable once
    # it has actually taken them off the socket.
    assert pump(lambda: len(compositor.requests_to(compositor.registry)) == len(_GLOBALS))
    return made


def announce(compositor, mirror, foreign: int,
             identifier: str, title: str, app_id: str) -> None:
    listing = compositor.bound(protocol.FOREIGN_LIST)
    compositor.send(listing, protocol.LIST_EVENT_TOPLEVEL, wire.new_id(foreign))
    compositor.send(foreign, protocol.FOREIGN_EVENT_IDENTIFIER, wire.string(identifier))
    compositor.send(foreign, protocol.FOREIGN_EVENT_TITLE, wire.string(title))
    compositor.send(foreign, protocol.FOREIGN_EVENT_APP_ID, wire.string(app_id))
    compositor.send(foreign, protocol.FOREIGN_EVENT_DONE)
    assert pump(lambda: any(t.identifier == identifier for t in mirror.toplevels()))


class TestBinding:
    def test_binds_every_protocol_it_needs(self, mirror, compositor):
        for interface in _GLOBALS:
            assert compositor.bound(interface)

    def test_caps_the_seat_to_version_one(self, mirror, compositor):
        for request in compositor.requests_to(compositor.registry):
            reader = wire.Reader(request.payload)
            reader.uint()
            if reader.string() == protocol.SEAT:
                assert reader.uint() == 1
                return
        raise AssertionError("wl_seat was never bound")

    def test_missing_protocol_is_refused(self, monkeypatch, qapp):
        without_manager = {name: version for name, version in _GLOBALS.items()
                           if name != protocol.MANAGER}
        bare = FakeCompositor(without_manager)
        bare.install(monkeypatch)
        connection = WaylandClient()
        try:
            with pytest.raises(WaylandError, match="no COSMIC toplevel management"):
                CosmicToplevels(connection, lambda: None)
        finally:
            connection.close()
            bare.close()

    def test_availability_is_answered_without_binding(self, client):
        assert CosmicToplevels.available(client) is True


class TestMirror:
    def test_records_an_announced_toplevel(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")

        toplevel = mirror.toplevels()[0]
        assert (toplevel.identifier, toplevel.title, toplevel.app_id) == (
            "id-a", "Firefox", "firefox")
        assert mirror.changes

    def test_upgrades_each_toplevel_to_a_cosmic_handle(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")

        upgrade, = compositor.requests_to(compositor.bound(protocol.INFO))
        assert upgrade.opcode == protocol.INFO_GET_COSMIC_TOPLEVEL
        reader = wire.Reader(upgrade.payload)
        assert (reader.new_id(), reader.object_id()) == (FIRST_HANDLE, FOREIGN_A)

    def test_decodes_state_flags(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Game", "steam_app_1")
        compositor.send(FIRST_HANDLE, protocol.HANDLE_EVENT_STATE,
                        _states(protocol.State.ACTIVATED, protocol.State.FULLSCREEN))
        assert pump(lambda: mirror.toplevels()[0].activated)

        toplevel = mirror.toplevels()[0]
        assert (toplevel.activated, toplevel.fullscreen, toplevel.minimized) == (
            True, True, False)

    def test_state_replaces_rather_than_accumulates(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Game", "steam_app_1")
        compositor.send(FIRST_HANDLE, protocol.HANDLE_EVENT_STATE,
                        _states(protocol.State.ACTIVATED))
        compositor.send(FIRST_HANDLE, protocol.HANDLE_EVENT_STATE,
                        _states(protocol.State.MINIMIZED))
        assert pump(lambda: mirror.toplevels()[0].minimized)

        toplevel = mirror.toplevels()[0]
        assert (toplevel.activated, toplevel.minimized) == (False, True)

    def test_title_change_is_picked_up(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Loading", "firefox")
        compositor.send(FOREIGN_A, protocol.FOREIGN_EVENT_TITLE, wire.string("Loaded"))
        compositor.send(FOREIGN_A, protocol.FOREIGN_EVENT_DONE)
        assert pump(lambda: mirror.toplevels()[0].title == "Loaded")

    def test_closed_toplevel_is_dropped_and_destroyed(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")

        compositor.send(FOREIGN_A, protocol.FOREIGN_EVENT_CLOSED)
        assert pump(lambda: mirror.toplevels() == [])

        destroyed = {(request.sender, request.opcode) for request in compositor.requests}
        assert (FIRST_HANDLE, protocol.HANDLE_DESTROY) in destroyed
        assert (FOREIGN_A, protocol.FOREIGN_HANDLE_DESTROY) in destroyed

    def test_tracks_several_toplevels_independently(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")
        announce(compositor, mirror, FOREIGN_B, "id-b", "Terminal", "term")
        compositor.send(FIRST_HANDLE + 1, protocol.HANDLE_EVENT_STATE,
                        _states(protocol.State.ACTIVATED))
        assert pump(lambda: any(t.activated for t in mirror.toplevels()))

        by_id = {t.identifier: t for t in mirror.toplevels()}
        assert by_id["id-a"].activated is False
        assert by_id["id-b"].activated is True

    def test_handle_for_maps_the_domain_id_to_the_control_handle(
            self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")
        assert mirror.handle_for("id-a") == FIRST_HANDLE
        assert mirror.handle_for("nobody") is None


class TestOperations:
    @pytest.fixture
    def opened(self, mirror, compositor):
        announce(compositor, mirror, FOREIGN_A, "id-a", "Firefox", "firefox")
        return mirror

    def _manager_requests(self, compositor):
        return [(request.opcode, request.payload)
                for request in compositor.requests_to(
                    compositor.bound(protocol.MANAGER))]

    def test_activate_restores_first_then_focuses(self, opened, compositor):
        seat = compositor.bound(protocol.SEAT)
        opened.activate(FIRST_HANDLE)
        assert pump(lambda: len(self._manager_requests(compositor)) == 2)

        assert self._manager_requests(compositor) == [
            (protocol.MANAGER_UNSET_MINIMIZED, wire.object_id(FIRST_HANDLE)),
            (protocol.MANAGER_ACTIVATE,
             wire.object_id(FIRST_HANDLE) + wire.object_id(seat)),
        ]

    def test_minimize(self, opened, compositor):
        opened.minimize(FIRST_HANDLE)
        assert pump(lambda: self._manager_requests(compositor) == [
            (protocol.MANAGER_SET_MINIMIZED, wire.object_id(FIRST_HANDLE))])

    def test_close(self, opened, compositor):
        opened.close_window(FIRST_HANDLE)
        assert pump(lambda: self._manager_requests(compositor) == [
            (protocol.MANAGER_CLOSE, wire.object_id(FIRST_HANDLE))])

    def test_a_broken_connection_does_not_escape(self, opened, compositor):
        compositor.hang_up()
        opened.minimize(FIRST_HANDLE)      # must not raise

    def test_a_protocol_error_does_not_escape(self, opened, compositor):
        compositor.send(
            1, 0,   # wl_display.error
            wire.object_id(FIRST_HANDLE), wire.uint(1), wire.string("bad handle"))
        assert pump(lambda: opened._client.is_closed)
        opened.minimize(FIRST_HANDLE)      # must not raise
