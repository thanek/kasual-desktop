"""Template-method base for platform `ProcessManager` adapters.

Both platform app managers track processes in an ``app_id -> proc`` dict, keyed
by each app's stable id rather than its tile position — a reorder or unpin
never touches this dict, and cleanup on process exit resolves the id back from
the dict itself. Subclasses implement only the spawn/kill/wait mechanics.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from domain.lifecycle.app_events import AppStarted, AppFinished, AppLaunchFailed
from domain.lifecycle.process_manager import ProcessManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from version import test_api_enabled

logger = logging.getLogger(__name__)


# Popen, or the Windows _WinHandle wrapper exposing the same pid/poll/wait/terminate surface.
Proc = Any


class BaseAppManager(QObject, ProcessManager, metaclass=ProtocolQtMeta):
    """Shared lifecycle bookkeeping for a multi-app `ProcessManager` adapter.

    Subclasses provide the platform-specific spawn/kill mechanics via the hook
    methods and the `launch` implementation. The base owns the per-app process
    dict, the lifecycle event emitters, the cross-thread finish hop, and all
    id-keyed queries (is_running / running_pid / ...).
    """

    _proc_ended = pyqtSignal(object, int)   # monitor thread -> GUI thread

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._processes: dict[str, Proc] = {}
        self._started_emitter = EventEmitter[AppStarted]()
        self._finished_emitter = EventEmitter[AppFinished]()
        self._launch_failed_emitter = EventEmitter[AppLaunchFailed]()
        self._proc_ended.connect(self._on_finished)

    # ── ProcessManager lifecycle events ──────────────────────────────────────

    def on_started(self, handler: Callable[[AppStarted], None]) -> Unsubscribe:
        return self._started_emitter.subscribe(handler)

    def on_finished(self, handler: Callable[[AppFinished], None]) -> Unsubscribe:
        return self._finished_emitter.subscribe(handler)

    def on_launch_failed(
        self, handler: Callable[[AppLaunchFailed], None]
    ) -> Unsubscribe:
        return self._launch_failed_emitter.subscribe(handler)

    # ── shared bookkeeping ────────────────────────────────────────────────────

    def is_running(self, app_id: str | None = None) -> bool:
        if app_id is not None:
            proc = self._processes.get(app_id)
            return proc is not None and proc.poll() is None
        return any(p.poll() is None for p in self._processes.values())

    def running_app_ids(self) -> list[str]:
        return [i for i, p in self._processes.items() if p.poll() is None]

    def running_pid(self, app_id: str) -> int | None:
        if self.is_running(app_id):
            return self._processes[app_id].pid
        return None

    def all_running_pids(self) -> list[int]:
        return [p.pid for p in self._processes.values() if p.poll() is None]

    def terminate(self, app_id: str) -> None:
        if not self.is_running(app_id):
            return
        proc = self._processes[app_id]
        logger.info("Ending app %s", app_id)
        try:
            self._terminate_proc(proc)
            QTimer.singleShot(3000, lambda: self._force_kill(proc))
        except Exception as e:
            logger.warning("Failed to terminate app %s: %s", app_id, e)

    # ── shared pre/post helpers for `launch` ──────────────────────────────────

    def _build_env(self, env: Mapping[str, str] | None) -> dict[str, str]:
        proc_env = os.environ.copy()
        self._prepare_env(proc_env)
        # In dev the flag is implied by the source checkout, never exported — hand it down.
        if test_api_enabled():
            proc_env["KD_TEST_API"] = "1"
        proc_env.update(env or {})
        return proc_env

    def _after_spawn(self, app_id: str, proc: Proc) -> bool:
        self._processes[app_id] = proc
        threading.Thread(
            target=self._monitor, args=(proc,), daemon=True
        ).start()
        self._started_emitter.emit(AppStarted(app_id))
        return True

    def _fail_launch(self, app_id: str, command: str, msg: str) -> bool:
        logger.error(msg)
        self._launch_failed_emitter.emit(AppLaunchFailed(app_id, msg))
        return False

    # ── shared monitoring / cleanup ───────────────────────────────────────────

    def _force_kill(self, proc: Proc) -> None:
        app_id = self._app_id_of(proc)
        if app_id is not None and proc.poll() is None:
            logger.warning("Force killing app %s", app_id)
            try:
                self._force_kill_proc(proc)
            except Exception as exc:
                logger.debug("Force kill of %s failed: %s", app_id, exc)

    def _monitor(self, proc: Proc) -> None:
        self._wait_for_exit(proc)
        self._proc_ended.emit(proc, proc.returncode)

    def _on_finished(self, proc: Proc, exit_code: int) -> None:
        app_id = self._app_id_of(proc)
        if app_id is None:
            return
        logger.info("Application %s ended (exit code=%d)", app_id, exit_code)
        self._processes.pop(app_id, None)
        self._finished_emitter.emit(AppFinished(app_id))

    def _app_id_of(self, proc: Proc) -> str | None:
        return next((i for i, p in self._processes.items() if p is proc), None)

    # ── platform hooks (override in subclasses) ───────────────────────────────

    def _prepare_env(self, proc_env: dict[str, str]) -> None:
        """Mutate *proc_env* with platform-specific tweaks before user overrides."""

    def _terminate_proc(self, proc: Proc) -> None:
        raise NotImplementedError

    def _force_kill_proc(self, proc: Proc) -> None:
        raise NotImplementedError

    def _wait_for_exit(self, proc: Proc) -> None:
        """Block until *proc* (and any platform siblings) have exited."""
        raise NotImplementedError
