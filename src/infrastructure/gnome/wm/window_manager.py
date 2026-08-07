"""WindowManager over the Kasual Helper GNOME Shell extension (D-Bus).

Mutter exposes no window-list protocol to clients, so the extension — running
inside the Shell with full Meta API access — reports the windows (with PIDs) and
performs the operations; this adapter polls ``ListWindows`` and forwards the
control calls. Same polling/cache/emitter shape as the other window managers.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.gnome import helper
from infrastructure.linux.proc import expand_pid_tree

logger = logging.getLogger(__name__)

# Mutter answers an activation it dislikes by doing nothing (see the extension's
# activationTime), so the ask is read back, and asked again.
_FOCUS_READBACK_MS = 400


class GnomeWindowManager(QObject, WindowManager, metaclass=ProtocolQtMeta):
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
        logger.debug("Windows list: %d, active: %s", len(self._cache), self._active_window_id)

    def _enum_windows(self) -> list[Window]:
        raw = helper.list_windows_json()
        if raw is None:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("ListWindows JSON error: %s", exc)
            return []
        windows: list[Window] = []
        for entry in data:
            pid = entry.get("pid") or 0
            wm_class = entry.get("wm_class") or ""
            if not wm_class or pid == self._our_pid:
                continue
            windows.append(Window(
                id=str(entry.get("id")),
                title=entry.get("title") or "",
                pid=pid,
                active=bool(entry.get("active")),
                resource_class=wm_class,
                desktop_file=entry.get("desktop_file") or "",
                fullscreen=bool(entry.get("fullscreen")),
            ))
        return windows

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

    # ── operations ─────────────────────────────────────────────────────────

    def activate_window(self, window_id: str) -> None:
        helper.call("ActivateWindow", window_id)

    def close_window(self, window_id: str) -> None:
        helper.call("CloseWindow", window_id)

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        owned = sorted(expand_pid_tree(pids))
        if owned:
            helper.call("MinimizeWindowsForPids", json.dumps(owned))

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        self._activate(pids, list(self._cache.values()), retries=1)

    def _activate(self, pids: set[int], windows: list[Window], retries: int) -> None:
        owned = expand_pid_tree(pids)
        wanted = [w.id for w in windows if w.pid in owned]
        for window_id in wanted:
            helper.call("ActivateWindow", window_id)
        if wanted and retries > 0:
            QTimer.singleShot(
                _FOCUS_READBACK_MS, lambda: self._reactivate_unfocused(pids, retries - 1))

    def _reactivate_unfocused(self, pids: set[int], retries: int) -> None:
        """A launched app that never took focus leaves Kasual reading its foreground off
        somebody else's window — and offering to close it."""
        windows = self._enum_windows()
        owned = expand_pid_tree(pids)
        if any(w.active for w in windows if w.pid in owned):
            return
        logger.warning("Activation ignored for pids %s; asking again", sorted(pids))
        self._activate(pids, windows, retries)

    def raise_self(self) -> None:
        # The extension keeps Kasual Desktop's surfaces pinned above; nothing to raise.
        pass

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        for w in self._cache.values():
            if w.pid == pid:
                helper.call("ActivateWindow", w.id)
