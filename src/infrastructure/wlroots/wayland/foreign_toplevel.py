"""The window list of a wlroots compositor, over
``zwlr_foreign_toplevel_management_v1`` — on labwc, wayfire and river the only
channel that both enumerates windows and accepts ``activate`` / ``close`` /
``set_minimized``.

Opcodes and state values are from ``wlr-protocols``,
``unstable/wlr-foreign-toplevel-management-unstable-v1.xml``. A toplevel is
identified by its object id and described by ``app_id`` and title; the protocol
never says which process it belongs to.
"""

from __future__ import annotations

import logging

from collections.abc import Callable
from dataclasses import dataclass, replace

from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient

logger = logging.getLogger(__name__)

MANAGER_INTERFACE = "zwlr_foreign_toplevel_manager_v1"
_SEAT_INTERFACE = "wl_seat"
_MANAGER_VERSION = 3

_MANAGER_EVENT_TOPLEVEL = 0
_MANAGER_EVENT_FINISHED = 1
_MANAGER_STOP = 0

_HANDLE_SET_MINIMIZED = 2
_HANDLE_UNSET_MINIMIZED = 3
_HANDLE_ACTIVATE = 4
_HANDLE_CLOSE = 5
_HANDLE_DESTROY = 7

_HANDLE_EVENT_TITLE = 0
_HANDLE_EVENT_APP_ID = 1
_HANDLE_EVENT_STATE = 4
_HANDLE_EVENT_DONE = 5
_HANDLE_EVENT_CLOSED = 6

_STATE_MAXIMIZED = 0
_STATE_MINIMIZED = 1
_STATE_ACTIVATED = 2
_STATE_FULLSCREEN = 3


@dataclass(frozen=True)
class ToplevelInfo:
    handle: int
    title: str = ""
    app_id: str = ""
    maximized: bool = False
    minimized: bool = False
    activated: bool = False
    fullscreen: bool = False


def _with_states(info: ToplevelInfo, states: list[int]) -> ToplevelInfo:
    return replace(
        info,
        maximized=_STATE_MAXIMIZED in states,
        minimized=_STATE_MINIMIZED in states,
        activated=_STATE_ACTIVATED in states,
        fullscreen=_STATE_FULLSCREEN in states,
    )


class ForeignToplevelManager:
    """Live view of the compositor's toplevels, and the requests that act on them.

    *on_changed* fires once per committed change (a handle appeared, updated or
    closed), never mid-update: the compositor sends title, app_id and state as
    separate events and only ``done`` means they belong together.
    """

    def __init__(
        self,
        client: WaylandClient,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self._on_changed = on_changed
        self._pending: dict[int, ToplevelInfo] = {}
        self._committed: dict[int, ToplevelInfo] = {}
        self._seat = (
            client.bind(_SEAT_INTERFACE, 1) if client.has_global(_SEAT_INTERFACE)
            else 0
        )
        self._manager = client.bind(
            MANAGER_INTERFACE, _MANAGER_VERSION, self._on_manager_event)
        client.roundtrip()

    @staticmethod
    def available(client: WaylandClient) -> bool:
        return client.has_global(MANAGER_INTERFACE)

    def snapshot(self) -> list[ToplevelInfo]:
        """Every mapped toplevel, in the order the compositor announced them."""
        return list(self._committed.values())

    # ── requests ─────────────────────────────────────────────────────────────

    def activate(self, handle: int) -> None:
        if not self._seat:
            logger.warning("No wl_seat bound; cannot activate toplevel %d", handle)
            return
        self._request(handle, _HANDLE_ACTIVATE, wire.object_id(self._seat))

    def close(self, handle: int) -> None:
        self._request(handle, _HANDLE_CLOSE)

    def set_minimized(self, handle: int) -> None:
        self._request(handle, _HANDLE_SET_MINIMIZED)

    def unset_minimized(self, handle: int) -> None:
        self._request(handle, _HANDLE_UNSET_MINIMIZED)

    def stop(self) -> None:
        self._client.send(self._manager, _MANAGER_STOP)
        self._forget_all()

    def _forget_all(self) -> None:
        for handle in self._pending:
            self._client.forget(handle)
        self._pending.clear()
        self._committed.clear()

    def _request(self, handle: int, opcode: int, *args: bytes) -> None:
        if handle not in self._pending:
            return
        self._client.send(handle, opcode, *args)

    # ── events ───────────────────────────────────────────────────────────────

    def _on_manager_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode == _MANAGER_EVENT_TOPLEVEL:
            handle = reader.new_id()
            self._pending[handle] = ToplevelInfo(handle)
            self._client.set_handler(
                handle, lambda op, rd: self._on_handle_event(handle, op, rd))
        elif opcode == _MANAGER_EVENT_FINISHED:
            # The manager object is dead here; only the local state is dropped.
            self._forget_all()
            self._changed()

    def _on_handle_event(self, handle: int, opcode: int, reader: wire.Reader) -> None:
        pending = self._pending.get(handle)
        if pending is None:
            return
        if opcode == _HANDLE_EVENT_TITLE:
            self._pending[handle] = replace(pending, title=reader.string())
        elif opcode == _HANDLE_EVENT_APP_ID:
            self._pending[handle] = replace(pending, app_id=reader.string())
        elif opcode == _HANDLE_EVENT_STATE:
            self._pending[handle] = _with_states(pending, reader.uint_array())
        elif opcode == _HANDLE_EVENT_DONE:
            self._committed[handle] = pending
            self._changed()
        elif opcode == _HANDLE_EVENT_CLOSED:
            del self._pending[handle]
            self._committed.pop(handle, None)
            self._client.send(handle, _HANDLE_DESTROY)
            self._client.forget(handle)
            self._changed()

    def _changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()
