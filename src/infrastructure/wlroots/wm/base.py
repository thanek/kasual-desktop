"""Shared skeletons for the wlroots window managers.

:class:`PollingWindowManager` holds what every backend here needs — the refresh
cycle, the window cache, the update emitter and the /proc PID expansion — and
:class:`WlrootsWindowManager` adds the JSON IPC CLI that Sway (``swaymsg``) and
Hyprland (``hyprctl``) are driven through. Compositors without such a CLI (labwc,
wayfire) build on the former and speak Wayland instead.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.linux.proc import expand_pid_tree

logger = logging.getLogger(__name__)

_CLI_TIMEOUT_S = 2.0


class PollingWindowManager(QObject, WindowManager, metaclass=ProtocolQtMeta):
    """Window manager built on a periodic re-enumeration. Subclasses implement
    ``_enum_windows`` and the imperative operations in the compositor's own terms."""

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


class WlrootsWindowManager(PollingWindowManager):
    """Polling window manager over a compositor's JSON IPC CLI."""

    def _run(self, args: list[str]) -> None:
        """Fire-and-forget CLI command; failures degrade to a logged warning."""
        try:
            subprocess.run(
                args, timeout=_CLI_TIMEOUT_S, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("%s failed: %s", args[0], exc)

    def _run_json(self, args: list[str]):
        """Run a CLI query and parse its JSON output, or None on any failure."""
        try:
            out = subprocess.run(
                args, timeout=_CLI_TIMEOUT_S, check=True,
                capture_output=True, text=True,
            ).stdout
            return json.loads(out)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            logger.warning("%s query failed: %s", args[0], exc)
            return None
