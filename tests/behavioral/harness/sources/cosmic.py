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

from PyQt6.QtCore import QObject, QSocketNotifier

from infrastructure.cosmic.wm import protocol
from infrastructure.cosmic.wm.pids import WindowPidResolver
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.linux.wayland.client import (
    Event, Interface, WaylandClient, words,
)
from tests.behavioral.harness.window_source import EventLog

logger = logging.getLogger(__name__)

_OUTPUT = 'wl_output'
_XDG_OUTPUT_MANAGER = 'zxdg_output_manager_v1'
_XDG_OUTPUT = 'zxdg_output_v1'

_XDG_OUTPUT_MANAGER_GET = 1

_INTERFACES = protocol.INTERFACES + (
    Interface(_OUTPUT, ()),
    Interface(_XDG_OUTPUT_MANAGER, ()),
    Interface(_XDG_OUTPUT, (
        Event('logical_position', 'ii'),
        Event('logical_size', 'ii'),
        Event('done'),
        Event('name', 's'),
        Event('description', 's'),
    )),
)


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
        self._notifier: QSocketNotifier | None = None
        self._list: int | None = None
        self._info: int | None = None

    def start(self, timeout_s: float) -> None:
        self._client = WaylandClient(_INTERFACES)
        self._list = self._client.bind(protocol.FOREIGN_LIST,
                                       protocol.FOREIGN_LIST_VERSION)
        self._info = self._client.bind(protocol.INFO, protocol.INFO_VERSION)
        if self._list is None or self._info is None:
            raise RuntimeError(
                'this compositor announces no COSMIC toplevel protocols — '
                'ext_foreign_toplevel_list_v1 and zcosmic_toplevel_info_v1')
        self._subscribe()
        self._watch_outputs()

        self._notifier = QSocketNotifier(
            self._client.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._drain)

        # Two: the first brings the toplevels, whose cosmic handles are requested
        # while it is being dispatched; their state and geometry follow in the second.
        self._client.roundtrip()
        self._client.roundtrip()
        self._snapshot('init')

    def stop(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── protocol ───────────────────────────────────────────────────────────

    def _subscribe(self) -> None:
        client = self._client
        client.on(protocol.FOREIGN_LIST, 'toplevel', self._on_toplevel)
        client.on(protocol.FOREIGN_HANDLE, 'identifier', self._on_identifier)
        client.on(protocol.FOREIGN_HANDLE, 'title', self._on_title)
        client.on(protocol.FOREIGN_HANDLE, 'app_id', self._on_app_id)
        client.on(protocol.FOREIGN_HANDLE, 'done', lambda _o: self._snapshot('done'))
        client.on(protocol.FOREIGN_HANDLE, 'closed', self._on_closed)
        client.on(protocol.HANDLE, 'state', self._on_state)
        client.on(protocol.HANDLE, 'geometry', self._on_geometry)
        client.on(_XDG_OUTPUT, 'logical_size', self._on_logical_size)

    def _watch_outputs(self) -> None:
        manager = self._client.bind(_XDG_OUTPUT_MANAGER, 3)
        if manager is None:
            logger.warning('no zxdg_output_manager_v1 — covers_screen stays False')
            return
        for output in self._client.bind_all(_OUTPUT, 4):
            xdg_output = self._client.new_id(_XDG_OUTPUT)
            self._client.request(manager, _XDG_OUTPUT_MANAGER_GET, xdg_output, output)
            self._output_of_xdg[xdg_output] = output

    def _drain(self) -> None:
        self._client.dispatch_pending()

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

    def _on_state(self, handle: int, raw: bytes) -> None:
        toplevel = self._toplevels.get(self._foreign_of.get(handle, -1))
        if toplevel is None:
            return
        states = set(words(raw))
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

    def _on_logical_size(self, xdg_output: int, width: int, height: int) -> None:
        output = self._output_of_xdg.get(xdg_output)
        if output is not None:
            self._output_size[output] = (width, height)

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
