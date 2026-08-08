"""A live mirror of cosmic-comp's toplevel list, plus the operations on it.

The compositor pushes the window world rather than answering queries about it, so
this keeps an up-to-date picture and calls ``on_change`` whenever it moves. The
window-manager adapter reads that picture instead of shelling out.

Each window is two protocol objects: the ext handle carrying identity (title,
app_id, identifier) and the cosmic handle carrying state and accepting the
management requests. They are paired on arrival and destroyed together.
"""

from __future__ import annotations

import logging

from collections.abc import Callable
from dataclasses import dataclass

from infrastructure.cosmic.wm import protocol
from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient, WaylandError

logger = logging.getLogger(__name__)

_REQUIRED = (protocol.FOREIGN_LIST, protocol.INFO, protocol.MANAGER, protocol.SEAT)


@dataclass
class Toplevel:
    identifier: str = ""
    title: str = ""
    app_id: str = ""
    activated: bool = False
    fullscreen: bool = False
    minimized: bool = False


class CosmicToplevels:
    """The compositor's toplevels as Kasual Desktop sees them, and the requests it
    sends.

    Raises :class:`WaylandError` from the constructor when the compositor does not
    implement the toplevel protocols, leaving the caller to degrade.
    """

    def __init__(self, client: WaylandClient, on_change: Callable[[], None]) -> None:
        self._client = client
        self._on_change = on_change
        self._toplevels: dict[int, Toplevel] = {}
        self._handle_of: dict[int, int] = {}     # ext handle → cosmic handle
        self._foreign_of: dict[int, int] = {}    # cosmic handle → ext handle

        missing = [name for name in _REQUIRED if not client.has_global(name)]
        if missing:
            raise WaylandError(
                f"compositor implements no COSMIC toplevel management: "
                f"missing {', '.join(missing)}")

        self._list = client.bind(
            protocol.FOREIGN_LIST, protocol.FOREIGN_LIST_VERSION, self._on_list_event)
        self._info = client.bind(protocol.INFO, protocol.INFO_VERSION)
        self._manager = client.bind(protocol.MANAGER, protocol.MANAGER_VERSION)
        self._seat = client.bind(protocol.SEAT, 1)
        # No roundtrip: waiting for the first window list would block the
        # composition root on compositor I/O. It arrives a moment later, and
        # ``on_change`` schedules the refresh that publishes it.

    @staticmethod
    def available(client: WaylandClient) -> bool:
        return all(client.has_global(name) for name in _REQUIRED)

    # ── reading ────────────────────────────────────────────────────────────

    def toplevels(self) -> list[Toplevel]:
        return list(self._toplevels.values())

    def handle_for(self, identifier: str) -> int | None:
        """The cosmic handle to send requests for, keyed by the domain window id."""
        for foreign, toplevel in self._toplevels.items():
            if toplevel.identifier == identifier:
                return self._handle_of.get(foreign)
        return None

    # ── operations ─────────────────────────────────────────────────────────

    def activate(self, handle: int) -> None:
        # A minimized window ignores activate; on a mapped one this is a no-op.
        self._request(protocol.MANAGER_UNSET_MINIMIZED, wire.object_id(handle))
        self._request(protocol.MANAGER_ACTIVATE,
                      wire.object_id(handle), wire.object_id(self._seat))

    def minimize(self, handle: int) -> None:
        self._request(protocol.MANAGER_SET_MINIMIZED, wire.object_id(handle))

    def close_window(self, handle: int) -> None:
        self._request(protocol.MANAGER_CLOSE, wire.object_id(handle))

    def _request(self, opcode: int, *args: bytes) -> None:
        self._client.send(self._manager, opcode, *args)

    # ── events ─────────────────────────────────────────────────────────────

    def _on_list_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode == protocol.LIST_EVENT_TOPLEVEL:
            self._add(reader.new_id())
        elif opcode == protocol.LIST_EVENT_FINISHED:
            # The list object is dead here; only the local mirror is dropped.
            self._toplevels.clear()
            self._handle_of.clear()
            self._foreign_of.clear()
            self._on_change()

    def _add(self, foreign: int) -> None:
        self._toplevels[foreign] = Toplevel()
        self._client.set_handler(
            foreign, lambda op, rd: self._on_foreign_event(foreign, op, rd))

        handle = self._client.allocate_id()
        self._client.set_handler(
            handle, lambda op, rd: self._on_handle_event(handle, op, rd))
        self._client.send(self._info, protocol.INFO_GET_COSMIC_TOPLEVEL,
                          wire.new_id(handle), wire.object_id(foreign))
        self._handle_of[foreign] = handle
        self._foreign_of[handle] = foreign

    def _on_foreign_event(self, foreign: int, opcode: int, reader: wire.Reader) -> None:
        toplevel = self._toplevels.get(foreign)
        if toplevel is None:
            return
        if opcode == protocol.FOREIGN_EVENT_TITLE:
            toplevel.title = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_APP_ID:
            toplevel.app_id = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_IDENTIFIER:
            toplevel.identifier = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_DONE:
            self._on_change()
        elif opcode == protocol.FOREIGN_EVENT_CLOSED:
            self._drop(foreign)

    def _on_handle_event(self, handle: int, opcode: int, reader: wire.Reader) -> None:
        if opcode != protocol.HANDLE_EVENT_STATE:
            return
        states = set(reader.uint_array())
        toplevel = self._toplevels.get(self._foreign_of.get(handle, -1))
        if toplevel is None:
            return
        toplevel.activated = protocol.State.ACTIVATED in states
        toplevel.fullscreen = protocol.State.FULLSCREEN in states
        toplevel.minimized = protocol.State.MINIMIZED in states
        self._on_change()

    def _drop(self, foreign: int) -> None:
        handle = self._handle_of.pop(foreign, None)
        if handle is not None:
            self._foreign_of.pop(handle, None)
            self._client.send(handle, protocol.HANDLE_DESTROY)
            self._client.forget(handle)
        self._client.send(foreign, protocol.FOREIGN_HANDLE_DESTROY)
        self._client.forget(foreign)
        self._toplevels.pop(foreign, None)
        self._on_change()
