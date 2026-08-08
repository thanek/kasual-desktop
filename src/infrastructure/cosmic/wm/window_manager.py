"""WindowManager over cosmic-comp's toplevel Wayland protocols.

Unlike Sway and Hyprland, COSMIC has a real minimize, so the port's
minimize/activate pair maps straight onto ``set_minimized``/``unset_minimized``
with no scratchpad or special-workspace stand-in. It has no fullscreen among its
management requests — cosmic-comp does not advertise that capability — so
:class:`ForegroundFullscreen` asks for it over X11 instead.

The compositor pushes changes instead of answering queries, so the mirror in
:class:`CosmicToplevels` is refreshed from the socket and the periodic snapshot
merely re-reads it — which is also when PIDs, unknowable from the protocol, are
resolved again.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QGuiApplication

from domain.catalog.window import Window
from infrastructure.cosmic.wm.fullscreen import ForegroundFullscreen
from infrastructure.cosmic.wm.pids import WindowPidResolver, representative_pid
from infrastructure.cosmic.wm.toplevels import CosmicToplevels
from infrastructure.cosmic.wm.xwayland import XWaylandWindows
from infrastructure.linux.proc import expand_pid_tree
from infrastructure.linux.wayland.client import WaylandClient
from infrastructure.linux.wm.base import PollingWindowManager

logger = logging.getLogger(__name__)


class CosmicWindowManager(PollingWindowManager):
    """Raises :class:`WaylandError` when the session offers no toplevel management."""

    def __init__(
        self, client: WaylandClient | None = None, parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client or WaylandClient()
        try:
            self._toplevels = CosmicToplevels(
                self._client, self._request_list_refresh)
        except Exception:
            # The connection is ours only when we opened it, but either way a
            # refused start must not leave a socket behind for the caller to
            # notice — it has only the exception to go on.
            self._client.close()
            raise
        self._xwayland = XWaylandWindows()
        self._pids = WindowPidResolver(self._xwayland)
        self._fullscreen = ForegroundFullscreen(self._xwayland)
        self._candidate_pids: dict[str, frozenset[int]] = {}
        self._client.start(on_disconnect=self._on_disconnect)

    def _on_disconnect(self) -> None:
        logger.warning("Wayland connection lost; the window list stops updating")
        self.stop_refresh()

    def _enum_windows(self) -> list[Window]:
        toplevels = self._toplevels.toplevels()
        x11 = self._xwayland.snapshot()
        self._candidate_pids = self._pids.resolve(toplevels, x11)
        self._fullscreen.apply(toplevels, x11)
        own_app_id = QGuiApplication.desktopFileName()
        windows = []
        for toplevel in toplevels:
            if not toplevel.identifier or not toplevel.app_id:
                continue
            # By app_id: our own PID is exactly what COSMIC will not tell us.
            if toplevel.app_id == own_app_id:
                continue
            candidates = self._candidate_pids.get(toplevel.identifier, frozenset())
            if candidates == {self._our_pid}:
                continue
            windows.append(Window(
                id=toplevel.identifier,
                title=toplevel.title,
                pid=representative_pid(candidates),
                active=toplevel.activated,
                fullscreen=toplevel.fullscreen,
                resource_class=toplevel.app_id,
            ))
        return windows

    def _windows_for_pids(self, pids: set[int]) -> list[Window]:
        """Windows any of whose candidate processes belong to *pids*' subtree.

        The base class compares one PID per window, which COSMIC often cannot pin
        down; membership of the tree needs no such choice. Two instances of one
        program share candidates and are reached together.
        """
        owned = expand_pid_tree(pids)
        return [w for w in self._cache.values()
                if self._candidate_pids.get(w.id, frozenset()) & owned]

    # ── operations ─────────────────────────────────────────────────────────

    def activate_window(self, window_id: str) -> None:
        handle = self._toplevels.handle_for(window_id)
        if handle is not None:
            self._toplevels.activate(handle)
        self._fullscreen.screen_given_to_app()

    def close_window(self, window_id: str) -> None:
        handle = self._toplevels.handle_for(window_id)
        if handle is not None:
            self._toplevels.close_window(handle)

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        for window in self._windows_for_pids(pids):
            handle = self._toplevels.handle_for(window.id)
            if handle is not None:
                self._toplevels.minimize(handle)

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        for window in self._windows_for_pids(pids):
            self.activate_window(window.id)

    def screen_given_to_app(self) -> None:
        self._fullscreen.screen_given_to_app()

    def raise_self(self) -> None:
        super().raise_self()
        self._fullscreen.screen_taken_back()

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        for window in self._cache.values():
            if pid in self._candidate_pids.get(window.id, frozenset()):
                self.activate_window(window.id)

    def close(self) -> None:
        super().close()
        self._client.close()
