"""WindowSource for COSMIC: the compositor's own toplevel protocols, pushed.

cosmic-comp has no IPC CLI to poll, which suits the harness — every change arrives
as an event, so a splash that lives between two polls still happened. The transport
(the minimal Wayland client) is shared with the shipped adapter the way the Sway
source shares `swaymsg` with its own; the picture built on top is the harness's,
so a bug in `CosmicToplevels` cannot hide itself here.

Two things the adapter does without are reconstructed for the assertions:

* **Geometry.** cosmic-comp reports a toplevel's rectangle only for outputs the
  client has bound, so every `wl_output` is bound and given a `zxdg_output_v1` to
  report its logical size — the same units the toplevel geometry arrives in, unlike
  `wl_output.mode`'s physical pixels.
* **PIDs.** No toplevel protocol carries one. The resolver is reused rather than
  re-derived, but only its unambiguous answers are taken: for the windows this suite
  inspects — games, which are XWayland — that is `_NET_WM_PID` off the X11 window, a
  fact rather than an inference. Anything the resolver could only guess at is
  reported as pid 0.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject

from infrastructure.cosmic.wm import protocol
from infrastructure.cosmic.wm.pids import WindowPidResolver
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient, WaylandError
from tests.behavioral.harness.window_source import EventLog

logger = logging.getLogger(__name__)

_OUTPUT = 'wl_output'
_XDG_OUTPUT_MANAGER = 'zxdg_output_manager_v1'

_XDG_OUTPUT_MANAGER_GET = 1

# zcosmic_toplevel_handle_v1 carries the rectangle the adapter does without.
_HANDLE_EVENT_GEOMETRY = 9

# zxdg_output_v1 events.
_XDG_OUTPUT_EVENT_LOGICAL_SIZE = 1


class CosmicWindowSource(QObject, EventLog):
    def __init__(self) -> None:
        QObject.__init__(self)
        EventLog.__init__(self)
        self._toplevels: dict[int, Toplevel] = {}
        self._geometry: dict[int, tuple[int, int, int, int]] = {}
        self._covers: dict[int, bool] = {}
        self._handle_of: dict[int, int] = {}
        self._foreign_of: dict[int, int] = {}
        self._output_of_xdg: dict[int, int] = {}
        self._output_size: dict[int, tuple[int, int]] = {}
        self._our_pid = os.getpid()
        self._pids = WindowPidResolver()
        self._client: WaylandClient | None = None
        self._list: int | None = None
        self._info: int | None = None

    def start(self, timeout_s: float) -> None:
        self._client = WaylandClient()
        try:
            self._list = self._client.bind(
                protocol.FOREIGN_LIST, protocol.FOREIGN_LIST_VERSION,
                self._on_list_event)
            self._info = self._client.bind(protocol.INFO, protocol.INFO_VERSION)
        except WaylandError as exc:
            raise RuntimeError(
                'this compositor announces no COSMIC toplevel protocols — '
                'ext_foreign_toplevel_list_v1 and zcosmic_toplevel_info_v1') from exc
        self._watch_outputs()
        self._client.start()

        # Two: the first brings the toplevels, whose cosmic handles are requested
        # while it is being dispatched; their state and geometry follow in the second.
        self._client.roundtrip()
        self._client.roundtrip()
        self._snapshot('init')

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── protocol ───────────────────────────────────────────────────────────

    def _watch_outputs(self) -> None:
        if not self._client.has_global(_XDG_OUTPUT_MANAGER):
            logger.warning('no zxdg_output_manager_v1 — covers_screen stays False')
            return
        manager = self._client.bind(_XDG_OUTPUT_MANAGER, 3)
        for output in self._client.bind_all(_OUTPUT, 4):
            xdg_output = self._client.allocate_id()
            self._client.set_handler(
                xdg_output,
                lambda op, rd, xdg=xdg_output: self._on_xdg_output_event(xdg, op, rd))
            self._client.send(manager, _XDG_OUTPUT_MANAGER_GET,
                              wire.new_id(xdg_output), wire.object_id(output))
            self._output_of_xdg[xdg_output] = output

    def _on_list_event(self, opcode: int, reader: wire.Reader) -> None:
        if opcode != protocol.LIST_EVENT_TOPLEVEL:
            return
        foreign = reader.new_id()
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
        if opcode == protocol.FOREIGN_EVENT_IDENTIFIER:
            toplevel.identifier = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_TITLE:
            toplevel.title = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_APP_ID:
            toplevel.app_id = reader.string()
        elif opcode == protocol.FOREIGN_EVENT_DONE:
            self._snapshot('done')
        elif opcode == protocol.FOREIGN_EVENT_CLOSED:
            self._on_closed(foreign)

    def _on_handle_event(self, handle: int, opcode: int, reader: wire.Reader) -> None:
        if opcode == protocol.HANDLE_EVENT_STATE:
            self._on_state(handle, reader.uint_array())
        elif opcode == _HANDLE_EVENT_GEOMETRY:
            self._on_geometry(
                handle, reader.object_id(),
                reader.int32(), reader.int32(), reader.int32(), reader.int32())

    def _on_xdg_output_event(
            self, xdg_output: int, opcode: int, reader: wire.Reader) -> None:
        if opcode != _XDG_OUTPUT_EVENT_LOGICAL_SIZE:
            return
        output = self._output_of_xdg.get(xdg_output)
        if output is not None:
            self._output_size[output] = (reader.int32(), reader.int32())

    def _on_state(self, handle: int, raw: list[int]) -> None:
        toplevel = self._toplevels.get(self._foreign_of.get(handle, -1))
        if toplevel is None:
            return
        states = set(raw)
        toplevel.activated = protocol.State.ACTIVATED in states
        toplevel.fullscreen = protocol.State.FULLSCREEN in states
        toplevel.minimized = protocol.State.MINIMIZED in states
        self._snapshot('state')

    def _on_geometry(self, handle: int, output: int, x: int, y: int,
                     width: int, height: int) -> None:
        foreign = self._foreign_of.get(handle)
        if foreign is None:
            return
        self._geometry[foreign] = (x, y, width, height)
        self._covers[foreign] = self._fills(output, width, height)
        self._snapshot('geometry')

    def _on_closed(self, foreign: int) -> None:
        handle = self._handle_of.pop(foreign, None)
        if handle is not None:
            self._foreign_of.pop(handle, None)
            self._client.forget(handle)
        self._client.forget(foreign)
        self._toplevels.pop(foreign, None)
        self._geometry.pop(foreign, None)
        self._covers.pop(foreign, None)
        self._snapshot('closed')

    def _fills(self, output: int, width: int, height: int) -> bool:
        size = self._output_size.get(output)
        return bool(size) and width >= size[0] and height >= size[1]

    # ── snapshots ──────────────────────────────────────────────────────────

    def _snapshot(self, reason: str) -> None:
        known = {foreign: toplevel for foreign, toplevel in self._toplevels.items()
                 if toplevel.identifier and toplevel.app_id}
        candidates = self._pids.resolve(list(known.values()))
        stack = []
        for foreign, toplevel in known.items():
            owners = candidates.get(toplevel.identifier, frozenset())
            pid = next(iter(owners)) if len(owners) == 1 else 0
            if pid == self._our_pid:
                continue
            stack.append({
                'id': toplevel.identifier,
                'title': toplevel.title,
                'app_id': toplevel.app_id,
                'pid': pid,
                'focused': toplevel.activated,
                'fullscreen': toplevel.fullscreen,
                'covers_screen': self._covers.get(foreign, False),
                'minimized': toplevel.minimized,
                'geometry': list(self._geometry.get(foreign, (0, 0, 0, 0))),
            })
        focused = next((w['id'] for w in stack if w['focused']), '')
        self.append(reason, focused, stack)
