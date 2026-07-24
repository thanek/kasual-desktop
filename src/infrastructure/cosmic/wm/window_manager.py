"""WindowManager over cosmic-comp's toplevel Wayland protocols.

Unlike Sway and Hyprland, COSMIC has a real minimize, so the port's
minimize/activate pair maps straight onto ``set_minimized``/``unset_minimized``
with no scratchpad or special-workspace stand-in. It has no client-driven
fullscreen — cosmic-comp does not advertise that capability — so a window is
activated and left to request fullscreen itself.

The compositor pushes changes instead of answering queries, so the mirror in
:class:`CosmicToplevels` is refreshed from the socket and the periodic snapshot
merely re-reads it — which is also when PIDs, unknowable from the protocol, are
resolved again for windows whose process has since become identifiable.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QSocketNotifier
from PyQt6.QtGui import QGuiApplication

from domain.catalog.window import Window
from infrastructure.cosmic.wm.pids import WindowPidResolver, representative_pid
from infrastructure.cosmic.wm.toplevels import CosmicToplevels
from infrastructure.linux.proc import expand_pid_tree
from infrastructure.linux.wm.base import PollingWindowManager


class CosmicWindowManager(PollingWindowManager):
    """Raises :class:`WaylandError` when the session offers no toplevel management."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._toplevels = CosmicToplevels(self._request_list_refresh)
        self._pids = WindowPidResolver()
        self._candidate_pids: dict[str, frozenset[int]] = {}
        self._notifier = QSocketNotifier(
            self._toplevels.fileno(), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._on_readable)

    def _on_readable(self) -> None:
        self._toplevels.dispatch()

    def _enum_windows(self) -> list[Window]:
        toplevels = self._toplevels.toplevels()
        self._candidate_pids = self._pids.resolve(toplevels)
        own_app_id = QGuiApplication.desktopFileName()
        windows = []
        for toplevel in toplevels:
            if not toplevel.identifier or not toplevel.app_id:
                continue
            # By app_id, not by PID: our own PID is exactly what COSMIC will not
            # tell us, and any Kasual surface that is not a layer-shell one — as
            # happens wherever LayerShellQt is missing — would otherwise come back
            # as a window of someone else's and earn itself a tile.
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

        The base class compares a window's single PID, which COSMIC often cannot
        pin down; asking whether the launched tree contains *any* candidate needs
        no such choice, and is the question the lifecycle is really posing. Two
        instances of one program share their candidates and so are reached
        together — the same over-reach ``matches_app`` already has, and far milder
        than leaving a launched app's own window unreachable.
        """
        owned = expand_pid_tree(pids)
        return [w for w in self._cache.values()
                if self._candidate_pids.get(w.id, frozenset()) & owned]

    # ── operations ─────────────────────────────────────────────────────────

    def activate_window(self, window_id: str) -> None:
        handle = self._toplevels.handle_for(window_id)
        if handle is not None:
            self._toplevels.activate(handle)

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

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        for window in self._cache.values():
            if pid in self._candidate_pids.get(window.id, frozenset()):
                self.activate_window(window.id)

    def close(self) -> None:
        self._notifier.setEnabled(False)
        self._toplevels.close()
        super().close()
