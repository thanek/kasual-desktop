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
from infrastructure.linux.wayland.client import WaylandClient, WaylandError, words

logger = logging.getLogger(__name__)


@dataclass
class Toplevel:
    identifier: str = ""
    title: str = ""
    app_id: str = ""
    activated: bool = False
    fullscreen: bool = False
    minimized: bool = False


class CosmicToplevels:
    """The compositor's toplevels as Kasual sees them, and the requests it sends.

    Raises :class:`WaylandError` from the constructor when the compositor does not
    implement the toplevel protocols, leaving the caller to degrade.
    """

    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self._toplevels: dict[int, Toplevel] = {}
        self._handle_of: dict[int, int] = {}     # ext handle → cosmic handle
        self._foreign_of: dict[int, int] = {}    # cosmic handle → ext handle

        self._client = WaylandClient(protocol.INTERFACES)
        self._list = self._client.bind(protocol.FOREIGN_LIST, protocol.FOREIGN_LIST_VERSION)
        self._info = self._client.bind(protocol.INFO, protocol.INFO_VERSION)
        self._manager = self._client.bind(protocol.MANAGER, protocol.MANAGER_VERSION)
        self._seat = self._client.bind(protocol.SEAT, 1)
        if None in (self._list, self._info, self._manager, self._seat):
            self._client.close()
            raise WaylandError("compositor implements no COSMIC toplevel management")

        # No roundtrip: the globals already answered whether this session can be
        # driven, and waiting for the first window list would block the composition
        # root on compositor I/O. The list arrives on the socket a moment later and
        # ``on_change`` schedules the refresh that publishes it.
        self._subscribe()

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
        # A minimized window ignores activate, so it is restored first; on an
        # already-mapped window unset_minimized is a no-op.
        self._request(protocol.MANAGER_UNSET_MINIMIZED, handle)
        self._request(protocol.MANAGER_ACTIVATE, handle, self._seat)

    def minimize(self, handle: int) -> None:
        self._request(protocol.MANAGER_SET_MINIMIZED, handle)

    def close_window(self, handle: int) -> None:
        self._request(protocol.MANAGER_CLOSE, handle)

    def _request(self, opcode: int, *args: int) -> None:
        try:
            self._client.request(self._manager, opcode, *args)
        except (OSError, WaylandError) as exc:
            logger.warning("COSMIC toplevel request %d failed: %s", opcode, exc)

    # ── connection plumbing ────────────────────────────────────────────────

    def fileno(self) -> int:
        return self._client.fileno()

    def dispatch(self) -> None:
        """Absorb whatever the compositor has pushed. Never raises: a protocol
        failure freezes the mirror rather than taking the Desktop down with it."""
        try:
            self._client.dispatch_pending()
        except (OSError, WaylandError) as exc:
            logger.warning("COSMIC toplevel stream failed: %s", exc)

    def close(self) -> None:
        self._client.close()

    # ── events ─────────────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        self._client.on(protocol.FOREIGN_LIST, "toplevel", self._on_toplevel)
        self._client.on(protocol.FOREIGN_HANDLE, "identifier", self._on_identifier)
        self._client.on(protocol.FOREIGN_HANDLE, "title", self._on_title)
        self._client.on(protocol.FOREIGN_HANDLE, "app_id", self._on_app_id)
        self._client.on(protocol.FOREIGN_HANDLE, "closed", self._on_closed)
        self._client.on(protocol.FOREIGN_HANDLE, "done", self._on_done)
        self._client.on(protocol.HANDLE, "state", self._on_state)

    def _on_toplevel(self, _list: int, foreign: int) -> None:
        self._toplevels[foreign] = Toplevel()
        handle = self._client.new_id(protocol.HANDLE)
        self._client.request(self._info, protocol.INFO_GET_COSMIC_TOPLEVEL,
                             handle, foreign)
        self._handle_of[foreign] = handle
        self._foreign_of[handle] = foreign

    def _on_identifier(self, foreign: int, identifier: str) -> None:
        self._toplevels[foreign].identifier = identifier

    def _on_title(self, foreign: int, title: str) -> None:
        self._toplevels[foreign].title = title

    def _on_app_id(self, foreign: int, app_id: str) -> None:
        self._toplevels[foreign].app_id = app_id

    def _on_done(self, _foreign: int) -> None:
        self._on_change()

    def _on_state(self, handle: int, raw: bytes) -> None:
        states = set(words(raw))
        toplevel = self._toplevels.get(self._foreign_of.get(handle, -1))
        if toplevel is None:
            return
        toplevel.activated = protocol.State.ACTIVATED in states
        toplevel.fullscreen = protocol.State.FULLSCREEN in states
        toplevel.minimized = protocol.State.MINIMIZED in states
        self._on_change()

    def _on_closed(self, foreign: int) -> None:
        handle = self._handle_of.pop(foreign, None)
        if handle is not None:
            self._foreign_of.pop(handle, None)
            self._client.request(handle, protocol.HANDLE_DESTROY)
            self._client.forget(handle)
        self._client.request(foreign, protocol.FOREIGN_HANDLE_DESTROY)
        self._client.forget(foreign)
        self._toplevels.pop(foreign, None)
        self._on_change()
