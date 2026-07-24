"""Cache, refresh and event plumbing shared by snapshot-based WindowManagers.

A compositor that can answer "which windows exist right now?" — over a JSON IPC
CLI (Sway, Hyprland) or from a mirrored Wayland protocol state (COSMIC) — needs
the same machinery around that one call: coalesced refreshes, the cache the
queries read, the active-window id and the update emitter. Subclasses supply
``_enum_windows`` and the compositor's imperative operations.
"""

from __future__ import annotations

import logging
import os

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.linux.proc import expand_pid_tree

logger = logging.getLogger(__name__)


class PollingWindowManager(QObject, WindowManager, metaclass=ProtocolQtMeta):
    """WindowManager driven by repeated whole-list snapshots."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._windows_emitter: EventEmitter[list[Window]] = EventEmitter()
        self._cache: dict[str, Window] = {}
        self._active_window_id: str | None = None
        self._our_pid = os.getpid()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._refresh_pending = False

    # ── refresh ────────────────────────────────────────────────────────────

    def start_periodic_refresh(self, interval_ms: int = 3000) -> None:
        self._request_list_refresh()
        self._refresh_timer.start(interval_ms)

    def stop_refresh(self) -> None:
        self._refresh_timer.stop()

    def refresh_now(self) -> None:
        self._request_list_refresh()

    def _request_list_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        windows = self._enum_windows()
        self._cache = {w.id: w for w in windows}
        self._active_window_id = next((w.id for w in windows if w.active), None)
        self._windows_emitter.emit(windows)
        self._after_refresh()
        logger.debug("Windows list: %d, active: %s", len(self._cache), self._active_window_id)

    def _after_refresh(self) -> None:
        """Extension point run on the freshly built cache; overridden where a
        compositor needs to react to its own window changes."""

    # ── queries ────────────────────────────────────────────────────────────

    def get_active_window_id(self) -> str | None:
        return self._active_window_id

    def get_cached_title(self, window_id: str) -> str | None:
        w = self._cache.get(window_id)
        return w.title if w else None

    def window_exists(self, window_id: str) -> bool:
        return window_id in self._cache

    def cached_windows(self) -> list[Window]:
        return list(self._cache.values())

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Unsubscribe:
        return self._windows_emitter.subscribe(handler)

    def close(self) -> None:
        self.stop_refresh()

    # ── shared operations ──────────────────────────────────────────────────

    def raise_self(self) -> None:
        # The Desktop is a layer-shell TOP surface; minimizing the foreground app
        # already uncovers it, so there is nothing to raise here.
        pass

    def _windows_for_pids(self, pids: set[int]) -> list[Window]:
        owned = expand_pid_tree(pids)
        return [w for w in self._cache.values() if w.pid in owned]

    # ── subclass contract ──────────────────────────────────────────────────

    def _enum_windows(self) -> list[Window]:
        raise NotImplementedError
