"""The Wayland wire format — framing and argument codecs.

A message is ``object_id: u32`` followed by ``(size << 16) | opcode: u32``, where
*size* counts the two header words too, and then the arguments. Everything is in
**host byte order** and every argument occupies a whole number of 4-byte words:

  ``uint`` / ``int`` / ``object`` / ``new_id``  one word
  ``fixed``                                     one word, signed 24.8
  ``string``                                    a length word (NUL included),
                                                then the bytes, padded
  ``array``                                     a length word, then the bytes,
                                                padded

``wl_registry.bind`` is the one request whose ``new_id`` names no interface in
the protocol; it carries the interface name and version inline instead
(:func:`new_id_bind`).
"""

from __future__ import annotations

import struct

from typing import NamedTuple

_WORD = struct.Struct("=I")
_INT = struct.Struct("=i")
HEADER_SIZE = 8


def _padded(length: int) -> int:
    return (length + 3) & ~3


# ── encoding ─────────────────────────────────────────────────────────────────

def uint(value: int) -> bytes:
    return _WORD.pack(value)


def int32(value: int) -> bytes:
    return _INT.pack(value)


def fixed(value: float) -> bytes:
    return _INT.pack(int(value * 256))


def object_id(value: int) -> bytes:
    """An object reference; 0 is the protocol's null."""
    return _WORD.pack(value)


def new_id(value: int) -> bytes:
    return _WORD.pack(value)


def string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\0"
    return _WORD.pack(len(raw)) + raw.ljust(_padded(len(raw)), b"\0")


def array(value: bytes) -> bytes:
    return _WORD.pack(len(value)) + value.ljust(_padded(len(value)), b"\0")


def new_id_bind(interface: str, version: int, target_id: int) -> bytes:
    """The untyped ``new_id`` of ``wl_registry.bind``: interface, version, id."""
    return string(interface) + uint(version) + new_id(target_id)


def encode_request(sender: int, opcode: int, *args: bytes) -> bytes:
    """Frame an already-encoded argument list as a request from *sender*."""
    payload = b"".join(args)
    size = HEADER_SIZE + len(payload)
    return _WORD.pack(sender) + _WORD.pack((size << 16) | opcode) + payload


# ── decoding ─────────────────────────────────────────────────────────────────

class Message(NamedTuple):
    sender: int
    opcode: int
    payload: bytes


def iter_messages(buffer: bytes) -> tuple[list[Message], bytes]:
    """Split *buffer* into complete messages and whatever tail is left.

    A socket read stops wherever the kernel had bytes, so the tail — possibly a
    header cut in half — is handed back for the next read to complete.
    """
    messages: list[Message] = []
    offset = 0
    while len(buffer) - offset >= HEADER_SIZE:
        sender = _WORD.unpack_from(buffer, offset)[0]
        word = _WORD.unpack_from(buffer, offset + 4)[0]
        size, opcode = word >> 16, word & 0xFFFF
        if size < HEADER_SIZE or len(buffer) - offset < size:
            break
        messages.append(
            Message(sender, opcode, buffer[offset + HEADER_SIZE:offset + size]))
        offset += size
    return messages, buffer[offset:]


class Reader:
    """Sequential reader over one message's arguments.

    Nothing on the wire says what type an argument is: the caller reads what the
    interface's XML declares. A read past the end raises ValueError rather than
    returning nonsense.
    """

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._offset = 0

    def uint(self) -> int:
        return self._word(_WORD)

    def int32(self) -> int:
        return self._word(_INT)

    def fixed(self) -> float:
        return self._word(_INT) / 256.0

    def object_id(self) -> int:
        return self._word(_WORD)

    def new_id(self) -> int:
        return self._word(_WORD)

    def string(self) -> str:
        raw = self._bytes()
        return raw[:-1].decode("utf-8", errors="replace") if raw else ""

    def array(self) -> bytes:
        return self._bytes()

    def uint_array(self) -> list[int]:
        """An array argument read as the u32 sequence it holds (e.g. window state)."""
        raw = self.array()
        whole_words = raw[:len(raw) - len(raw) % 4]
        return [value for (value,) in _WORD.iter_unpack(whole_words)]

    def _word(self, fmt: struct.Struct) -> int:
        if self._offset + 4 > len(self._payload):
            raise ValueError("truncated Wayland message")
        value = fmt.unpack_from(self._payload, self._offset)[0]
        self._offset += 4
        return value

    def _bytes(self) -> bytes:
        length = self._word(_WORD)
        end = self._offset + length
        if end > len(self._payload):
            raise ValueError("truncated Wayland message")
        raw = self._payload[self._offset:end]
        self._offset += _padded(length)
        return raw
