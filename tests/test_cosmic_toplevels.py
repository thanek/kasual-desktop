"""Tests for the COSMIC toplevel mirror, driven through a fake compositor.

The point is protocol fidelity: the opcodes are positional in the protocol XML, so
these assert the exact bytes that go out and the exact events that come back.
"""

from unittest.mock import patch

import pytest

from infrastructure.cosmic.wm import protocol
from infrastructure.cosmic.wm.toplevels import CosmicToplevels
from infrastructure.linux.wayland.client import WaylandError
from tests import wayland_wire as wire

_GLOBALS = (
    (protocol.FOREIGN_LIST, protocol.FOREIGN_LIST_VERSION),
    (protocol.INFO, protocol.INFO_VERSION),
    (protocol.MANAGER, protocol.MANAGER_VERSION),
    (protocol.SEAT, 9),
)

# Object ids the client hands out: 2 registry, 3 sync callback, then the binds in
# the order CosmicToplevels performs them, then the cosmic handles.
LIST_ID, INFO_ID, MANAGER_ID, SEAT_ID = 4, 5, 6, 7
FIRST_HANDLE = 8

FOREIGN_A = 0xFF000000
FOREIGN_B = 0xFF000001


@pytest.fixture
def compositor():
    fake = wire.FakeCompositor()
    yield fake
    fake.close()


def build(compositor, globals_=_GLOBALS):
    """A mirror whose opening registry roundtrip is already answered."""
    compositor.send(
        *(wire.advertise(i, name, version)
          for i, (name, version) in enumerate(globals_)),
        wire.callback_done(3),
    )
    changes = []
    with patch("infrastructure.linux.wayland.client._display_socket",
               return_value=compositor.client):
        mirror = CosmicToplevels(lambda: changes.append(True))
    return mirror, changes


def announce(compositor, foreign: int, identifier: str, title: str, app_id: str):
    compositor.send(
        wire.message(LIST_ID, 0, wire.word(foreign)),
        wire.message(foreign, 4, wire.text(identifier)),
        wire.message(foreign, 2, wire.text(title)),
        wire.message(foreign, 3, wire.text(app_id)),
        wire.message(foreign, 1),
    )


class TestBinding:
    def test_binds_every_protocol_it_needs(self, compositor):
        build(compositor)
        bound = [body for obj, opcode, body in compositor.received()
                 if obj == wire.REGISTRY_ID and opcode == 0]
        assert len(bound) == len(_GLOBALS)

    def test_caps_the_seat_to_version_one(self, compositor):
        build(compositor)
        seat = [body for obj, opcode, body in compositor.received()
                if obj == wire.REGISTRY_ID and opcode == 0
                and protocol.SEAT.encode() in body][0]
        assert seat.endswith(wire.word(1) + wire.word(SEAT_ID))

    def test_missing_protocol_is_refused(self, compositor):
        without_manager = tuple(g for g in _GLOBALS if g[0] != protocol.MANAGER)
        with pytest.raises(WaylandError, match="no COSMIC toplevel management"):
            build(compositor, without_manager)


class TestMirror:
    def test_records_an_announced_toplevel(self, compositor):
        mirror, changes = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        mirror.dispatch()

        toplevel = mirror.toplevels()[0]
        assert (toplevel.identifier, toplevel.title, toplevel.app_id) == (
            "id-a", "Firefox", "firefox")
        assert changes

    def test_upgrades_each_toplevel_to_a_cosmic_handle(self, compositor):
        mirror, _ = build(compositor)
        compositor.received()
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        mirror.dispatch()

        assert (INFO_ID, protocol.INFO_GET_COSMIC_TOPLEVEL,
                wire.word(FIRST_HANDLE) + wire.word(FOREIGN_A)) \
            in compositor.received()

    def test_decodes_state_flags(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Game", "steam_app_1")
        compositor.send(wire.message(FIRST_HANDLE, 8, wire.array(
            [protocol.State.ACTIVATED, protocol.State.FULLSCREEN])))
        mirror.dispatch()

        toplevel = mirror.toplevels()[0]
        assert (toplevel.activated, toplevel.fullscreen, toplevel.minimized) == (
            True, True, False)

    def test_state_replaces_rather_than_accumulates(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Game", "steam_app_1")
        compositor.send(
            wire.message(FIRST_HANDLE, 8, wire.array([protocol.State.ACTIVATED])),
            wire.message(FIRST_HANDLE, 8, wire.array([protocol.State.MINIMIZED])))
        mirror.dispatch()

        toplevel = mirror.toplevels()[0]
        assert (toplevel.activated, toplevel.minimized) == (False, True)

    def test_title_change_is_picked_up(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Loading", "firefox")
        compositor.send(wire.message(FOREIGN_A, 2, wire.text("Loaded")),
                        wire.message(FOREIGN_A, 1))
        mirror.dispatch()
        assert mirror.toplevels()[0].title == "Loaded"

    def test_closed_toplevel_is_dropped_and_destroyed(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        mirror.dispatch()
        compositor.received()

        compositor.send(wire.message(FOREIGN_A, 0))
        mirror.dispatch()

        assert mirror.toplevels() == []
        destroyed = {(obj, opcode) for obj, opcode, _ in compositor.received()}
        assert (FIRST_HANDLE, protocol.HANDLE_DESTROY) in destroyed
        assert (FOREIGN_A, protocol.FOREIGN_HANDLE_DESTROY) in destroyed

    def test_tracks_several_toplevels_independently(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        announce(compositor, FOREIGN_B, "id-b", "Terminal", "term")
        compositor.send(wire.message(FIRST_HANDLE + 1, 8,
                                     wire.array([protocol.State.ACTIVATED])))
        mirror.dispatch()

        by_id = {t.identifier: t for t in mirror.toplevels()}
        assert by_id["id-a"].activated is False
        assert by_id["id-b"].activated is True

    def test_handle_for_maps_the_domain_id_to_the_control_handle(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        mirror.dispatch()
        assert mirror.handle_for("id-a") == FIRST_HANDLE
        assert mirror.handle_for("nobody") is None


class TestOperations:
    def _mirror(self, compositor):
        mirror, _ = build(compositor)
        announce(compositor, FOREIGN_A, "id-a", "Firefox", "firefox")
        mirror.dispatch()
        compositor.received()
        return mirror

    def test_activate_restores_first_then_focuses(self, compositor):
        mirror = self._mirror(compositor)
        mirror.activate(FIRST_HANDLE)
        assert compositor.received() == [
            (MANAGER_ID, protocol.MANAGER_UNSET_MINIMIZED, wire.word(FIRST_HANDLE)),
            (MANAGER_ID, protocol.MANAGER_ACTIVATE,
             wire.word(FIRST_HANDLE) + wire.word(SEAT_ID)),
        ]

    def test_minimize(self, compositor):
        mirror = self._mirror(compositor)
        mirror.minimize(FIRST_HANDLE)
        assert compositor.received() == [
            (MANAGER_ID, protocol.MANAGER_SET_MINIMIZED, wire.word(FIRST_HANDLE))]

    def test_close(self, compositor):
        mirror = self._mirror(compositor)
        mirror.close_window(FIRST_HANDLE)
        assert compositor.received() == [
            (MANAGER_ID, protocol.MANAGER_CLOSE, wire.word(FIRST_HANDLE))]

    def test_a_broken_connection_does_not_escape(self, compositor):
        mirror = self._mirror(compositor)
        compositor.close()
        mirror.minimize(FIRST_HANDLE)      # must not raise

    def test_dispatch_survives_a_protocol_error(self, compositor):
        mirror = self._mirror(compositor)
        compositor.send(wire.message(
            wire.DISPLAY_ID, 0,
            wire.word(FIRST_HANDLE) + wire.word(1) + wire.text("bad handle")))
        mirror.dispatch()                  # must not raise
