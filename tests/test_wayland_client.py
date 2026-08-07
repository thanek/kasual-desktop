"""Tests for the private Wayland connection, against a compositor stand-in
(``tests/wayland_fake.py``) on a socketpair — no compositor is contacted."""

import pytest

from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import DISPLAY_ID, WaylandClient, WaylandError
from wayland_fake import FakeCompositor, pump

_DISPLAY_EVENT_ERROR = 0
_DISPLAY_EVENT_DELETE_ID = 1
_SEAT = "wl_seat"


@pytest.fixture
def compositor(monkeypatch):
    fake = FakeCompositor({_SEAT: 5, "zwlr_foreign_toplevel_manager_v1": 3})
    fake.install(monkeypatch)
    yield fake
    fake.close()


@pytest.fixture
def client(compositor, qapp):
    connection = WaylandClient()
    yield connection
    connection.close()


class TestConnecting:
    def test_collects_the_globals_the_compositor_announced(self, client):
        assert client.globals() == {
            _SEAT: (1, 5), "zwlr_foreign_toplevel_manager_v1": (2, 3)}

    def test_has_global_answers_for_what_is_missing(self, client):
        assert client.has_global(_SEAT)
        assert not client.has_global("wl_shm")

    def test_without_a_socket_it_refuses_to_connect(self, monkeypatch):
        monkeypatch.delenv("WAYLAND_SOCKET", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-does-not-exist")
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/nonexistent")
        with pytest.raises(WaylandError):
            WaylandClient()

    def test_without_a_runtime_dir_it_refuses_to_connect(self, monkeypatch):
        monkeypatch.delenv("WAYLAND_SOCKET", raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
        with pytest.raises(WaylandError):
            WaylandClient()


class TestBinding:
    def test_bind_sends_the_interface_and_returns_its_object_id(self, client, compositor):
        seat = client.bind(_SEAT, 5)
        client.roundtrip()
        assert compositor.bound(_SEAT) == seat

    def test_bind_caps_the_version_at_what_is_advertised(self, client, compositor):
        client.bind("zwlr_foreign_toplevel_manager_v1", 9)
        client.roundtrip()
        request = compositor.requests_to(compositor.registry)[0]
        reader = wire.Reader(request.payload)
        reader.uint(), reader.string()
        assert reader.uint() == 3

    def test_binding_a_missing_interface_is_an_error(self, client):
        with pytest.raises(WaylandError):
            client.bind("wl_shm", 1)


class TestEvents:
    def test_dispatches_to_the_object_that_bound_the_handler(self, client, compositor):
        received = []
        seat = client.bind(_SEAT, 5, lambda opcode, reader: received.append(opcode))
        client.start()
        client.roundtrip()

        compositor.send(seat, 3)
        assert pump(lambda: received == [3])

    def test_an_event_for_a_forgotten_object_is_ignored(self, client, compositor):
        received = []
        seat = client.bind(_SEAT, 5, lambda opcode, reader: received.append(opcode))
        client.start()
        client.roundtrip()
        client.forget(seat)

        compositor.send(seat, 3)
        assert not pump(lambda: bool(received), timeout_s=0.2)

    def test_delete_id_forgets_the_object(self, client, compositor):
        received = []
        seat = client.bind(_SEAT, 5, lambda opcode, reader: received.append(opcode))
        client.start()
        client.roundtrip()

        compositor.send(DISPLAY_ID, _DISPLAY_EVENT_DELETE_ID, wire.uint(seat))
        compositor.send(seat, 3)
        assert not pump(lambda: bool(received), timeout_s=0.2)

    def test_a_malformed_event_does_not_break_the_connection(self, client, compositor):
        seat = client.bind(_SEAT, 5, lambda opcode, reader: reader.string())
        client.start()
        client.roundtrip()

        compositor.send(seat, 0, wire.uint(1))
        assert not pump(lambda: client.is_closed, timeout_s=0.2)


class TestDisconnecting:
    def test_a_protocol_error_closes_the_connection(self, client, compositor):
        lost = []
        client.start(on_disconnect=lambda: lost.append(True))

        compositor.send(DISPLAY_ID, _DISPLAY_EVENT_ERROR,
                        wire.object_id(DISPLAY_ID), wire.uint(1),
                        wire.string("invalid method"))
        assert pump(lambda: client.is_closed)
        assert lost == [True]

    def test_the_compositor_hanging_up_closes_the_connection(self, client, compositor):
        lost = []
        client.start(on_disconnect=lambda: lost.append(True))

        compositor.hang_up()
        assert pump(lambda: client.is_closed)
        assert lost == [True]

    def test_sending_after_close_is_ignored(self, client):
        client.close()
        client.send(DISPLAY_ID, 0)
        assert client.is_closed

    def test_close_is_idempotent(self, client):
        client.close()
        client.close()
        assert client.is_closed
