"""WindowSource for wlroots compositors without an IPC CLI (labwc, wayfire).

The compositor pushes every window change over
``wlr-foreign-toplevel-management``, on a Wayland connection of the harness's own
— so a splash that lives between two polls is still seen.

What the protocol cannot give is geometry: there is no window rectangle and no
output size, so ``covers_screen`` is always False here and a window counts as
holding the screen only when it says it is fullscreen. The pid is resolved from
/proc the same way the production backend does it, and stays 0 when nothing
matches.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QObject

from infrastructure.linux.wayland.client import WaylandClient
from infrastructure.linux.wayland.pid_lookup import AppIdPidResolver
from infrastructure.wlroots.wayland.foreign_toplevel import ForeignToplevelManager
from tests.behavioral.harness.window_source import EventLog


class ForeignToplevelWindowSource(QObject, EventLog):
    def __init__(self) -> None:
        QObject.__init__(self)
        EventLog.__init__(self)
        self._client: WaylandClient | None = None
        self._toplevels: ForeignToplevelManager | None = None
        self._pids = AppIdPidResolver()
        self._our_pid = os.getpid()

    def start(self, timeout_s: float) -> None:
        self._client = WaylandClient()
        if not ForeignToplevelManager.available(self._client):
            raise RuntimeError(
                'this compositor does not offer wlr-foreign-toplevel-management — '
                'the harness cannot read its windows')
        self._toplevels = ForeignToplevelManager(self._client)
        self._toplevels.observe(self._on_change)
        self._client.start()
        self._snapshot('init')

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _on_change(self) -> None:
        self._snapshot('change')

    def _snapshot(self, reason: str) -> None:
        infos = self._toplevels.snapshot()
        pids = self._pids.resolve([info.app_id for info in infos])
        stack = [
            {
                'id':            str(info.handle),
                'title':         info.title,
                'app_id':        info.app_id,
                'pid':           pids[info.app_id],
                'focused':       info.activated,
                'fullscreen':    info.fullscreen,
                'covers_screen': False,
                'floating':      False,
                'geometry':      [0, 0, 0, 0],
            }
            for info in infos
            if pids[info.app_id] != self._our_pid
        ]
        focused = next((w['id'] for w in stack if w['focused']), '')
        self.append(reason, focused, stack)
