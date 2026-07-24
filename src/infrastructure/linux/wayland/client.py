"""A minimal Wayland wire-protocol client.

Some compositors publish window management only as a Wayland protocol — no IPC
CLI (Sway, Hyprland), no scripting engine (KWin), no extension host (GNOME). No
Python binding to libwayland is packaged on the distros Kasual targets, so the
handful of interfaces it needs are spoken directly over the display socket.

Only what those interfaces use is implemented: requests whose arguments are all
32-bit words (object ids, new ids, uints) plus the registry's ``bind``, and
events decoded from a declarative :class:`Interface` table. Anything arriving for
an unknown object or opcode is skipped, so a newer compositor adding events stays
harmless.
"""

from __future__ import annotations

import logging
import os
import socket
import struct

from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("=IHH")     # object id, then opcode and size packed in one word
_WORD = struct.Struct("=I")
_INT = struct.Struct("=i")

_DISPLAY_ID = 1
_DISPLAY_SYNC = 0
_DISPLAY_GET_REGISTRY = 1
_REGISTRY_BIND = 0


@dataclass(frozen=True)
class Event:
    """One event of an interface. Position in :attr:`Interface.events` is the opcode.

    ``signature`` uses the Wayland type letters this client supports: ``i`` int,
    ``u`` uint, ``o`` object, ``n`` new id, ``s`` string, ``a`` array. ``creates``
    names the interface of a server-allocated ``n`` argument, so the connection can
    route that object's own events without the caller registering it.
    """

    name: str
    signature: str = ""
    creates: str = ""


@dataclass(frozen=True)
class Interface:
    name: str
    events: tuple[Event, ...] = ()


_WL_DISPLAY = Interface("wl_display", (
    Event("error", "uus"),
    Event("delete_id", "u"),
))

_WL_REGISTRY = Interface("wl_registry", (
    Event("global", "usu"),
    Event("global_remove", "u"),
))

_WL_CALLBACK = Interface("wl_callback", (Event("done", "u"),))


def _pad(length: int) -> int:
    return (length + 3) & ~3


def _word(value: int) -> bytes:
    return _WORD.pack(value & 0xFFFFFFFF)


def _string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\0"
    return _WORD.pack(len(raw)) + raw.ljust(_pad(len(raw)), b"\0")


def _display_socket() -> socket.socket:
    """Connect to the compositor the way libwayland does.

    ``WAYLAND_SOCKET`` hands over an already-connected fd (how a compositor spawns
    a client); otherwise ``WAYLAND_DISPLAY`` names a socket under the runtime dir,
    or is an absolute path of its own.
    """
    inherited = os.environ.get("WAYLAND_SOCKET")
    if inherited:
        del os.environ["WAYLAND_SOCKET"]
        return socket.socket(fileno=int(inherited))
    display = os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
    if not os.path.isabs(display):
        display = os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), display)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(display)
    return sock


class WaylandError(Exception):
    """The compositor rejected something we sent — always a bug in our encoding."""


@dataclass
class _Global:
    name: int
    version: int


class WaylandClient:
    """A connection to the compositor, speaking the interfaces it is told about.

    Construction performs the initial registry roundtrip, so :meth:`bind` sees the
    full set of globals immediately.
    """

    def __init__(self, interfaces: tuple[Interface, ...] = ()) -> None:
        self._interfaces = {
            i.name: i for i in (_WL_DISPLAY, _WL_REGISTRY, _WL_CALLBACK, *interfaces)
        }
        self._interface_of: dict[int, str] = {_DISPLAY_ID: _WL_DISPLAY.name}
        self._handlers: dict[tuple[str, str], Callable[..., None]] = {}
        # A list per interface: wl_output and wl_seat are advertised once per device.
        self._globals: dict[str, list[_Global]] = {}
        self._next_id = _DISPLAY_ID + 1
        self._inbox = b""
        self._sock = _display_socket()

        self.on(_WL_REGISTRY.name, "global", self._remember_global)
        self.on(_WL_REGISTRY.name, "global_remove", self._forget_global)
        self.on(_WL_DISPLAY.name, "error", self._on_error)
        self.on(_WL_DISPLAY.name, "delete_id", self._on_delete_id)

        self._registry = self.new_id(_WL_REGISTRY.name)
        self.request(_DISPLAY_ID, _DISPLAY_GET_REGISTRY, self._registry)
        self.roundtrip()

    # ── object bookkeeping ─────────────────────────────────────────────────

    def new_id(self, interface: str) -> int:
        """Reserve a client-side object id for *interface*."""
        object_id = self._next_id
        self._next_id += 1
        self._interface_of[object_id] = interface
        return object_id

    def forget(self, object_id: int) -> None:
        """Drop a destroyed object, so late events for it are ignored."""
        self._interface_of.pop(object_id, None)

    def on(self, interface: str, event: str, handler: Callable[..., None]) -> None:
        """Route *event* of *interface* to *handler*, called as ``handler(object_id, *args)``."""
        self._handlers[(interface, event)] = handler

    # ── requests ───────────────────────────────────────────────────────────

    def request(self, object_id: int, opcode: int, *args: int) -> None:
        """Send a request whose arguments are all 32-bit words."""
        self._send(object_id, opcode, b"".join(_word(a) for a in args))

    def bind(self, interface: str, version: int) -> int | None:
        """Bind a global at up to *version*, or None if the compositor lacks it."""
        bound = self.bind_all(interface, version)
        return bound[0] if bound else None

    def bind_all(self, interface: str, version: int) -> list[int]:
        """Bind every advertised instance of *interface* — one per output or seat."""
        object_ids = []
        for advertised in self._globals.get(interface, ()):
            object_id = self.new_id(interface)
            self._send(self._registry, _REGISTRY_BIND,
                       _word(advertised.name) + _string(interface)
                       + _word(min(version, advertised.version)) + _word(object_id))
            object_ids.append(object_id)
        return object_ids

    def _send(self, object_id: int, opcode: int, body: bytes) -> None:
        self._sock.sendall(_HEADER.pack(object_id, opcode, _HEADER.size + len(body)) + body)

    # ── reading ────────────────────────────────────────────────────────────

    def fileno(self) -> int:
        return self._sock.fileno()

    def dispatch_pending(self) -> None:
        """Consume and dispatch whatever has already arrived, without blocking."""
        while True:
            try:
                chunk = self._sock.recv(65536, socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
            except OSError as exc:
                logger.warning("Wayland connection lost: %s", exc)
                break
            if not chunk:
                break
            self._inbox += chunk
            self._drain()

    def roundtrip(self) -> None:
        """Block until the compositor has handled every request sent so far."""
        callback = self.new_id(_WL_CALLBACK.name)
        done = False

        def on_done(_object_id: int, _data: int) -> None:
            nonlocal done
            done = True

        self.on(_WL_CALLBACK.name, "done", on_done)
        self.request(_DISPLAY_ID, _DISPLAY_SYNC, callback)
        while not done:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise WaylandError("compositor closed the connection")
            self._inbox += chunk
            self._drain()
        self.forget(callback)

    def close(self) -> None:
        self._sock.close()

    def _drain(self) -> None:
        while len(self._inbox) >= _HEADER.size:
            object_id, opcode, size = _HEADER.unpack_from(self._inbox)
            if len(self._inbox) < size:
                return
            body = self._inbox[_HEADER.size:size]
            self._inbox = self._inbox[size:]
            self._dispatch(object_id, opcode, body)

    def _dispatch(self, object_id: int, opcode: int, body: bytes) -> None:
        interface = self._interfaces.get(self._interface_of.get(object_id, ""))
        if interface is None or opcode >= len(interface.events):
            return
        event = interface.events[opcode]
        args = _decode(event.signature, body)
        if event.creates and args:
            self._interface_of[args[0]] = event.creates
        handler = self._handlers.get((interface.name, event.name))
        if handler is not None:
            handler(object_id, *args)

    # ── built-in handlers ──────────────────────────────────────────────────

    def _remember_global(self, _registry: int, name: int, interface: str,
                         version: int) -> None:
        self._globals.setdefault(interface, []).append(_Global(name, version))

    def _forget_global(self, _registry: int, name: int) -> None:
        for advertised in self._globals.values():
            for entry in list(advertised):
                if entry.name == name:
                    advertised.remove(entry)

    def _on_error(self, _display: int, object_id: int, code: int, message: str) -> None:
        raise WaylandError(f"object {object_id} code {code}: {message}")

    def _on_delete_id(self, _display: int, object_id: int) -> None:
        self.forget(object_id)


def words(raw: bytes) -> tuple[int, ...]:
    """A Wayland array read as the 32-bit values it carries — how enum arrays such
    as a toplevel's state or a manager's capabilities are encoded."""
    return struct.unpack(f"={len(raw) // 4}I", raw[:len(raw) // 4 * 4])


def _decode(signature: str, body: bytes) -> list:
    args: list = []
    offset = 0
    for kind in signature:
        if kind in "sa":
            length, = _WORD.unpack_from(body, offset)
            offset += _WORD.size
            raw = body[offset:offset + length]
            offset += _pad(length)
            args.append(raw.decode("utf-8", "replace").rstrip("\0")
                        if kind == "s" else raw)
        elif kind == "i":
            args.append(_INT.unpack_from(body, offset)[0])
            offset += _INT.size
        else:
            args.append(_WORD.unpack_from(body, offset)[0])
            offset += _WORD.size
    return args
