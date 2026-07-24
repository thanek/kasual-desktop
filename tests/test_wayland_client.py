"""Tests for the minimal Wayland wire-protocol client.

A socket pair stands in for the compositor, so the encoder and the event decoder
are exercised against real bytes rather than a mock.
"""

from unittest.mock import patch

import pytest

from infrastructure.linux.wayland.client import (
    Event, Interface, WaylandClient, WaylandError,
)
from tests import wayland_wire as wire

_THING = Interface("test_thing", (
    Event("closed"),
    Event("named", "s"),
    Event("counted", "uia"),
    Event("spawned", "n", creates="test_child"),
))
_CHILD = Interface("test_child", (Event("pinged", "u"),))

_CALLBACK_ID = 3     # the client allocates 2 for the registry, then 3 to sync


@pytest.fixture
def compositor():
    fake = wire.FakeCompositor()
    yield fake
    fake.close()


def connect(compositor, *globals_, interfaces=(_THING, _CHILD)) -> WaylandClient:
    """A client whose opening roundtrip is already answered."""
    compositor.send(*globals_, wire.callback_done(_CALLBACK_ID))
    with patch("infrastructure.linux.wayland.client._display_socket",
               return_value=compositor.client):
        return WaylandClient(interfaces)


class TestHandshake:
    def test_asks_for_the_registry_and_syncs(self, compositor):
        connect(compositor)
        sent = compositor.received()
        assert sent[0][:2] == (wire.DISPLAY_ID, 1)      # get_registry
        assert sent[1][:2] == (wire.DISPLAY_ID, 0)      # sync

    def test_dead_socket_fails_the_way_the_factory_expects(self, compositor):
        # build_window_manager() catches (OSError, WaylandError) to degrade to the
        # null backend; a compositor that is simply not there must land in there.
        compositor.server.close()
        with patch("infrastructure.linux.wayland.client._display_socket",
                   return_value=compositor.client):
            with pytest.raises((OSError, WaylandError)):
                WaylandClient(())

    def test_roundtrip_raises_when_the_compositor_hangs_up(self, compositor):
        client = connect(compositor)
        compositor.hang_up()
        with pytest.raises(WaylandError, match="closed the connection"):
            client.roundtrip()


class TestBind:
    def test_binds_an_advertised_global(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 4))
        compositor.received()
        object_id = client.bind("test_thing", 4)

        _, opcode, body = compositor.received()[0]
        assert opcode == 0
        assert body == wire.word(7) + wire.text("test_thing") + wire.word(4) \
            + wire.word(object_id)

    def test_caps_the_version_to_what_is_advertised(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 2))
        compositor.received()
        client.bind("test_thing", 9)
        assert compositor.received()[0][2].endswith(
            wire.word(2) + wire.word(client._next_id - 1))

    def test_missing_global_binds_to_nothing(self, compositor):
        client = connect(compositor)
        assert client.bind("test_thing", 1) is None
        assert client.bind_all("test_thing", 1) == []

    def test_bind_all_covers_every_advertised_instance(self, compositor):
        # wl_output is advertised once per monitor, wl_seat once per seat.
        client = connect(compositor, wire.advertise(7, "test_thing", 1),
                         wire.advertise(8, "test_thing", 1))
        compositor.received()
        assert len(client.bind_all("test_thing", 1)) == 2
        names = [body[:4] for _, _, body in compositor.received()]
        assert names == [wire.word(7), wire.word(8)]

    def test_bind_takes_the_first_of_several(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1),
                         wire.advertise(8, "test_thing", 1))
        compositor.received()
        client.bind("test_thing", 1)
        assert compositor.received()[0][2][:4] == wire.word(7)

    def test_removed_global_can_no_longer_be_bound(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        compositor.send(wire.message(wire.REGISTRY_ID, 1, wire.word(7)))
        client.dispatch_pending()
        assert client.bind("test_thing", 1) is None


class TestEventDecoding:
    def _listen(self, client, interface, event):
        seen = []
        client.on(interface, event, lambda *args: seen.append(args))
        return seen

    def test_decodes_a_string(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = self._listen(client, "test_thing", "named")
        compositor.send(wire.message(thing, 1, wire.text("zażółć gęślą")))
        client.dispatch_pending()
        assert seen == [(thing, "zażółć gęślą")]

    def test_decodes_mixed_arguments(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = self._listen(client, "test_thing", "counted")
        compositor.send(wire.message(
            thing, 2, wire.word(5) + wire.integer(-9) + wire.array([1, 2, 3])))
        client.dispatch_pending()
        assert seen[0][1:3] == (5, -9)
        assert seen[0][3] == wire.array([1, 2, 3])[4:]

    def test_several_messages_in_one_read(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = self._listen(client, "test_thing", "named")
        compositor.send(wire.message(thing, 1, wire.text("one")),
                        wire.message(thing, 1, wire.text("two")))
        client.dispatch_pending()
        assert [s[1] for s in seen] == ["one", "two"]

    def test_unknown_opcode_is_ignored(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = self._listen(client, "test_thing", "named")
        compositor.send(wire.message(thing, 99, b""))
        client.dispatch_pending()
        assert seen == []

    def test_events_for_an_unknown_object_are_ignored(self, compositor):
        client = connect(compositor)
        seen = self._listen(client, "test_thing", "named")
        compositor.send(wire.message(4242, 1, wire.text("nobody")))
        client.dispatch_pending()
        assert seen == []


class TestObjectLifetime:
    def test_server_created_object_is_adopted_and_routed(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        pinged = []
        client.on("test_child", "pinged", lambda *args: pinged.append(args))

        child_id = 0xFF000000
        compositor.send(wire.message(thing, 3, wire.word(child_id)),
                        wire.message(child_id, 0, wire.word(42)))
        client.dispatch_pending()
        assert pinged == [(child_id, 42)]

    def test_forgotten_object_stops_being_routed(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = []
        client.on("test_thing", "named", lambda *args: seen.append(args))
        client.forget(thing)
        compositor.send(wire.message(thing, 1, wire.text("gone")))
        client.dispatch_pending()
        assert seen == []

    def test_delete_id_forgets_the_object(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        seen = []
        client.on("test_thing", "named", lambda *args: seen.append(args))
        compositor.send(wire.message(wire.DISPLAY_ID, 1, wire.word(thing)),
                        wire.message(thing, 1, wire.text("gone")))
        client.dispatch_pending()
        assert seen == []


class TestRequests:
    def test_words_are_sent_in_order(self, compositor):
        client = connect(compositor, wire.advertise(7, "test_thing", 1))
        thing = client.bind("test_thing", 1)
        compositor.received()
        client.request(thing, 2, 11, 22, 33)
        assert compositor.received() == [
            (thing, 2, wire.word(11) + wire.word(22) + wire.word(33))]

    def test_protocol_error_is_raised(self, compositor):
        client = connect(compositor)
        compositor.send(wire.message(
            wire.DISPLAY_ID, 0, wire.word(7) + wire.word(3) + wire.text("bad object")))
        with pytest.raises(WaylandError, match="bad object"):
            client.dispatch_pending()
