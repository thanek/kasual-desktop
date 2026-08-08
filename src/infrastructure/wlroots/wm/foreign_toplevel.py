"""WindowManager for wlroots compositors with no IPC CLI — labwc, wayfire, river.

The window list arrives over ``wlr-foreign-toplevel-management`` (see
:mod:`infrastructure.wlroots.wayland.foreign_toplevel`) rather than from a CLI,
so it is pushed: every committed change re-enumerates, and the inherited timer is
only a safety net.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject

from domain.catalog.window import Window
from infrastructure.linux.proc import expand_pid_tree, process_name
from infrastructure.linux.wayland.client import WaylandClient, WaylandError
from infrastructure.linux.wayland.pid_lookup import (
    MIN_NAME_LENGTH, AppIdPidResolver, app_id_keys,
)
from infrastructure.wlroots.wayland.foreign_toplevel import ForeignToplevelManager
from infrastructure.linux.wm.base import PollingWindowManager

logger = logging.getLogger(__name__)


class ForeignToplevelWindowManager(PollingWindowManager):
    def __init__(
        self,
        client: WaylandClient,
        pid_resolver: AppIdPidResolver | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._pids = pid_resolver or AppIdPidResolver()
        self._toplevels = ForeignToplevelManager(client)
        self._toplevels.observe(self._request_list_refresh)
        client.start(on_disconnect=self._on_disconnect)

    def _enum_windows(self) -> list[Window]:
        infos = self._toplevels.snapshot()
        pids = self._pids.resolve([info.app_id for info in infos])
        return [
            Window(
                id=str(info.handle),
                title=info.title,
                pid=pids.get(info.app_id, 0),
                active=info.activated,
                fullscreen=info.fullscreen,
                resource_class=info.app_id,
            )
            for info in infos
        ]

    def activate_window(self, window_id: str) -> None:
        handle = _handle(window_id)
        self._toplevels.unset_minimized(handle)
        self._toplevels.activate(handle)

    def close_window(self, window_id: str) -> None:
        self._toplevels.close(_handle(window_id))

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        for window in self._windows_for_pids(pids):
            self._toplevels.set_minimized(_handle(window.id))

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        for window in self._windows_for_pids(pids):
            self.activate_window(window.id)

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        for window in self._cache.values():
            if window.pid == pid:
                self.activate_window(window.id)

    def close(self) -> None:
        super().close()
        self._client.close()

    def _windows_for_pids(self, pids: set[int]) -> list[Window]:
        """Windows of the process subtree *pids*: by pid where one was resolved, and
        by app id against the subtree's process names where none was."""
        owned = expand_pid_tree(pids)
        names = {(process_name(pid) or "").lower() for pid in owned} - {""}
        return [w for w in self._cache.values()
                if w.pid in owned
                or (not w.pid and _named_by(w.resource_class, names))]

    def _on_disconnect(self) -> None:
        logger.warning("Wayland connection lost; the window list stops updating")
        self.stop_refresh()


def _named_by(app_id: str, process_names: set[str]) -> bool:
    """Whether *app_id* is plausibly one of *process_names*. Either side may be the
    prefix: comm is kernel-truncated to 15 characters, and an app id is often the
    launcher of a longer-named binary."""
    keys = [key for key in app_id_keys(app_id) if len(key) >= MIN_NAME_LENGTH]
    return any(key.startswith(name) or name.startswith(key)
               for key in keys
               for name in process_names if len(name) >= MIN_NAME_LENGTH)


def _handle(window_id: str) -> int:
    return int(window_id)


def build(parent: QObject | None = None) -> ForeignToplevelWindowManager | None:
    """The backend, or None where the compositor offers no toplevel manager."""
    try:
        client = WaylandClient()
    except WaylandError as exc:
        logger.warning("No Wayland connection of our own: %s", exc)
        return None
    if not ForeignToplevelManager.available(client):
        logger.warning("Compositor does not offer wlr-foreign-toplevel-management")
        client.close()
        return None
    return ForeignToplevelWindowManager(client, parent=parent)
