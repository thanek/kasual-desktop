"""A fake compositor on a socket pair, for the Wayland client tests.

Encodes the wire format independently of the code under test — the point is to
catch an encoding that drifts, so the two must not share an implementation.
"""

import socket
import struct

_HEADER = struct.Struct("=IHH")

DISPLAY_ID = 1
REGISTRY_ID = 2


def message(object_id: int, opcode: int, body: bytes = b"") -> bytes:
    return _HEADER.pack(object_id, opcode, _HEADER.size + len(body)) + body


def word(value: int) -> bytes:
    return struct.pack("=I", value & 0xFFFFFFFF)


def integer(value: int) -> bytes:
    return struct.pack("=i", value)


def text(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\0"
    padded = raw.ljust((len(raw) + 3) & ~3, b"\0")
    return struct.pack("=I", len(raw)) + padded


def array(values) -> bytes:
    raw = b"".join(word(v) for v in values)
    return struct.pack("=I", len(raw)) + raw


def advertise(name: int, interface: str, version: int) -> bytes:
    """A ``wl_registry.global`` event."""
    return message(REGISTRY_ID, 0, word(name) + text(interface) + word(version))


def callback_done(callback_id: int) -> bytes:
    return message(callback_id, 0, word(0))


def parse(raw: bytes) -> list[tuple[int, int, bytes]]:
    """Split a client's output into ``(object_id, opcode, body)`` messages."""
    out = []
    while len(raw) >= _HEADER.size:
        object_id, opcode, size = _HEADER.unpack_from(raw)
        out.append((object_id, opcode, raw[_HEADER.size:size]))
        raw = raw[size:]
    return out


class FakeCompositor:
    """The server end of a socket pair, pre-loaded with what the client will read."""

    def __init__(self) -> None:
        self.server, self.client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    def send(self, *messages: bytes) -> None:
        self.server.sendall(b"".join(messages))

    def hang_up(self) -> None:
        """Stop sending but keep receiving, so the client reads EOF mid-conversation
        instead of having its next write refused."""
        self.server.shutdown(socket.SHUT_WR)

    def received(self) -> list[tuple[int, int, bytes]]:
        try:
            return parse(self.server.recv(65536, socket.MSG_DONTWAIT))
        except BlockingIOError:
            return []

    def close(self) -> None:
        self.server.close()
        self.client.close()
