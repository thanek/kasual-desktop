"""A minimal Wayland client — a second connection to the compositor.

Qt exposes nothing of the connection it holds, so a protocol Qt does not
implement is spoken over one of our own; the compositor simply sees a second
client. Implemented here are ``wl_display`` (sync, error, delete_id),
``wl_registry`` (the globals and ``bind``), and dispatch to whatever proxies bind
on top. There is no scanner-generated code: every opcode is a named constant
read off the protocol's XML.

Events arrive through a QSocketNotifier, so the connection lives on the Qt event
loop with no thread and no polling; :meth:`roundtrip` is the one blocking call,
for wiring up before the loop runs.
"""

from __future__ import annotations

import errno
import logging
import os
import socket

from collections.abc import Callable

from PyQt6.QtCore import QObject, QSocketNotifier

from infrastructure.linux.wayland import wire

logger = logging.getLogger(__name__)

DISPLAY_ID = 1

# wl_display requests / events, and wl_registry's, from wayland.xml.
_DISPLAY_SYNC = 0
_DISPLAY_GET_REGISTRY = 1
_DISPLAY_EVENT_ERROR = 0
_DISPLAY_EVENT_DELETE_ID = 1
_REGISTRY_BIND = 0
_REGISTRY_EVENT_GLOBAL = 0
_REGISTRY_EVENT_GLOBAL_REMOVE = 1

_ROUNDTRIP_TIMEOUT_S = 2.0

EventHandler = Callable[[int, wire.Reader], None]
"""Called with an event's opcode and a reader over its arguments."""


class WaylandError(RuntimeError):
    """The connection could not be established, or the compositor killed it."""


class WaylandClient(QObject):
    """One Wayland connection: object ids, the registry, and event dispatch."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket = _connect()
        self._buffer = b""
        self._next_id = DISPLAY_ID + 1
        self._handlers: dict[int, EventHandler] = {}
        self._globals: dict[str, tuple[int, int]] = {}   # interface → (name, version)
        self._notifier: QSocketNotifier | None = None
        self._closed = False
        self._on_disconnect: Callable[[], None] | None = None

        self._handlers[DISPLAY_ID] = self._on_display_event
        registry = self.allocate_id()
        self._handlers[registry] = self._on_registry_event
        self.send(DISPLAY_ID, _DISPLAY_GET_REGISTRY, wire.new_id(registry))
        self._registry = registry
        self.roundtrip()

    # ── connection ───────────────────────────────────────────────────────────

    def start(self, on_disconnect: Callable[[], None] | None = None) -> None:
        """Deliver events through the Qt event loop from here on."""
        if self._closed or self._notifier is not None:
            return
        self._on_disconnect = on_disconnect
        self._notifier = QSocketNotifier(
            self._socket.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(lambda _fd: self._read_available())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        try:
            self._socket.close()
        except OSError:
            pass

    @property
    def is_closed(self) -> bool:
        return self._closed

    # ── objects and the registry ─────────────────────────────────────────────

    def allocate_id(self) -> int:
        """Reserve the next client-side object id. The protocol allows reusing one
        the compositor has deleted; nothing here needs to, so ids only ever grow."""
        object_id = self._next_id
        self._next_id += 1
        return object_id

    def globals(self) -> dict[str, tuple[int, int]]:
        return dict(self._globals)

    def has_global(self, interface: str) -> bool:
        return interface in self._globals

    def bind(
        self,
        interface: str,
        version: int,
        handler: EventHandler | None = None,
    ) -> int:
        """Bind *interface* at min(*version*, what the compositor offers).

        Asking for more than the advertised version is a protocol error that
        kills the connection, so the request is capped instead.
        """
        advertised = self._globals.get(interface)
        if advertised is None:
            raise WaylandError(f"compositor does not offer {interface}")
        name, available = advertised
        object_id = self.allocate_id()
        if handler is not None:
            self._handlers[object_id] = handler
        self.send(
            self._registry, _REGISTRY_BIND,
            wire.uint(name),
            wire.new_id_bind(interface, min(version, available), object_id),
        )
        return object_id

    def set_handler(self, object_id: int, handler: EventHandler) -> None:
        """Route events for a server-created object (e.g. a toplevel handle)."""
        self._handlers[object_id] = handler

    def forget(self, object_id: int) -> None:
        self._handlers.pop(object_id, None)

    # ── traffic ──────────────────────────────────────────────────────────────

    def send(self, sender: int, opcode: int, *args: bytes) -> None:
        if self._closed:
            return
        try:
            self._socket.sendall(wire.encode_request(sender, opcode, *args))
        except OSError as exc:
            logger.warning("Wayland send failed: %s", exc)
            self._disconnected()

    def roundtrip(self) -> None:
        """Block until the compositor has processed everything sent so far.

        ``wl_display.sync`` replies on a one-shot callback, so its arrival proves
        every earlier request was handled — which is how the registry's globals
        are known to be complete.
        """
        if self._closed:
            return
        done = False

        def _on_callback(_opcode: int, _reader: wire.Reader) -> None:
            nonlocal done
            done = True

        callback = self.allocate_id()
        self._handlers[callback] = _on_callback
        self.send(DISPLAY_ID, _DISPLAY_SYNC, wire.new_id(callback))

        self._socket.settimeout(_ROUNDTRIP_TIMEOUT_S)
        try:
            while not done and not self._closed:
                if not self._read_once():
                    break
        finally:
            if not self._closed:
                self._socket.settimeout(None)
            self._handlers.pop(callback, None)
        if not done:
            logger.warning("Wayland roundtrip did not complete")

    def _read_available(self) -> None:
        """Drain whatever the notifier woke us for, without blocking."""
        self._socket.setblocking(False)
        while self._read_once():
            pass

    def _read_once(self) -> bool:
        """Read one chunk and dispatch the messages it completes.

        False means nothing more can be read right now — the socket is drained,
        it timed out, or the connection is gone.
        """
        if self._closed:
            return False
        try:
            chunk = self._socket.recv(4096)
        except (BlockingIOError, TimeoutError):
            # TimeoutError only while roundtrip() has a timeout set; both mean
            # "nothing more to read", not a broken connection.
            return False
        except OSError as exc:
            if exc.errno == errno.EINTR:
                return True
            logger.warning("Wayland read failed: %s", exc)
            self._disconnected()
            return False
        if not chunk:
            logger.info("Wayland connection closed by the compositor")
            self._disconnected()
            return False
        self._buffer += chunk
        messages, self._buffer = wire.iter_messages(self._buffer)
        for message in messages:
            if self._closed:
                return False
            self._dispatch(message)
        return True

    def _dispatch(self, message: wire.Message) -> None:
        handler = self._handlers.get(message.sender)
        if handler is None:
            return   # an object we destroyed, or never cared about
        try:
            handler(message.opcode, wire.Reader(message.payload))
        except ValueError as exc:
            logger.warning("Malformed Wayland event for object %d: %s",
                           message.sender, exc)

    def _disconnected(self) -> None:
        if self._closed:
            return
        notify = self._on_disconnect
        self.close()
        if notify is not None:
            notify()

    # ── core objects ─────────────────────────────────────────────────────────

    def _on_display_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode == _DISPLAY_EVENT_ERROR:
            object_id, code = reader.object_id(), reader.uint()
            logger.error("Wayland protocol error on object %d (code %d): %s",
                         object_id, code, reader.string())
            self._disconnected()
        elif opcode == _DISPLAY_EVENT_DELETE_ID:
            self.forget(reader.uint())

    def _on_registry_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode == _REGISTRY_EVENT_GLOBAL:
            name, interface, version = reader.uint(), reader.string(), reader.uint()
            self._globals[interface] = (name, version)
        elif opcode == _REGISTRY_EVENT_GLOBAL_REMOVE:
            name = reader.uint()
            for interface, (advertised, _version) in list(self._globals.items()):
                if advertised == name:
                    del self._globals[interface]


def _connect() -> socket.socket:
    """Connect the way libwayland does: an inherited fd first, then the socket
    path — absolute display names are used as-is."""
    inherited = os.environ.get("WAYLAND_SOCKET")
    if inherited:
        try:
            return socket.socket(fileno=int(inherited))
        except (OSError, ValueError) as exc:
            raise WaylandError(f"WAYLAND_SOCKET={inherited!r} unusable: {exc}") from exc

    display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    if not os.path.isabs(display):
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime_dir:
            raise WaylandError("XDG_RUNTIME_DIR is unset; no Wayland socket to find")
        display = os.path.join(runtime_dir, display)
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(display)
    except OSError as exc:
        raise WaylandError(f"cannot connect to {display}: {exc}") from exc
    return client
