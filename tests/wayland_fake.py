"""A compositor stand-in for the Wayland client tests.

It speaks the wire protocol over a socketpair the client is handed through
``WAYLAND_SOCKET``: it answers ``wl_display.sync`` (without which the client's
opening roundtrip would just time out), announces the globals it was given, and
records every request for the test to assert on.

Serving runs on a thread because the client's roundtrip blocks; sends are
serialised so a reply cannot interleave with an event pushed from the test.
"""

from __future__ import annotations

import socket
import threading
import time

from PyQt6.QtCore import QCoreApplication

from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import DISPLAY_ID

_DISPLAY_SYNC = 0
_DISPLAY_GET_REGISTRY = 1
_REGISTRY_GLOBAL = 0
_CALLBACK_DONE = 0


class FakeCompositor:
    def __init__(self, globals_: dict[str, int] | None = None) -> None:
        self.globals = globals_ or {}
        self.requests: list[wire.Message] = []
        self.registry = 0
        self._server, client = socket.socketpair()
        self._client_fd = client.detach()
        self._send_lock = threading.Lock()
        self._buffer = b""
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def install(self, monkeypatch) -> None:
        """Point the next WaylandClient at this compositor."""
        monkeypatch.setenv("WAYLAND_SOCKET", str(self._client_fd))

    def close(self) -> None:
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)

    def hang_up(self) -> None:
        self._server.shutdown(socket.SHUT_RDWR)

    # ── outgoing ─────────────────────────────────────────────────────────────

    def send(self, sender: int, opcode: int, *args: bytes) -> None:
        with self._send_lock:
            try:
                self._server.sendall(wire.encode_request(sender, opcode, *args))
            except OSError:
                pass

    def announce(self, interface: str, version: int, name: int) -> None:
        self.send(self.registry, _REGISTRY_GLOBAL,
                  wire.uint(name), wire.string(interface), wire.uint(version))

    # ── incoming ─────────────────────────────────────────────────────────────

    def requests_to(self, sender: int) -> list[wire.Message]:
        return [request for request in self.requests if request.sender == sender]

    def bound(self, interface: str) -> int:
        """The object id the client's bind of *interface* allocated."""
        for request in self.requests_to(self.registry):
            reader = wire.Reader(request.payload)
            reader.uint()
            if reader.string() == interface:
                reader.uint()
                return reader.new_id()
        raise AssertionError(f"{interface} was never bound")

    def _serve(self) -> None:
        while True:
            try:
                chunk = self._server.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            self._buffer += chunk
            messages, self._buffer = wire.iter_messages(self._buffer)
            for message in messages:
                self._handle(message)

    def _handle(self, message: wire.Message) -> None:
        self.requests.append(message)
        if message.sender != DISPLAY_ID:
            return
        if message.opcode == _DISPLAY_GET_REGISTRY:
            self.registry = wire.Reader(message.payload).new_id()
            for index, (interface, version) in enumerate(self.globals.items(), start=1):
                self.announce(interface, version, index)
        elif message.opcode == _DISPLAY_SYNC:
            self.send(wire.Reader(message.payload).new_id(), _CALLBACK_DONE,
                      wire.uint(1))


def pump(condition, timeout_s: float = 1.0) -> bool:
    """Spin the Qt event loop until *condition* holds — how the client's
    QSocketNotifier gets a chance to deliver."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        QCoreApplication.processEvents()
        time.sleep(0.005)
    return condition()
