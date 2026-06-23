"""Template-method base for platform `ProcessManager` adapters.

Both the Windows and KDE app managers track concurrent child processes in an
``idx -> proc`` dict, fire the same started/finished/launch-failed emitters,
and key all post-launch cleanup on process identity (so a tile reorder or a
close+relaunch re-keying the dict does not put a stale timer on the wrong pid).
That bookkeeping is identical across platforms; only the actual spawn/kill/wait
mechanics differ. This base owns the shared lifecycle; subclasses override the
small hooks ``_spawn`` / ``_terminate_proc`` / ``_force_kill_proc`` /
``_wait_for_exit`` / ``_prepare_env`` and the top-level ``launch`` (which
expresses the platform-specific launch strategy and delegates the common
post-spawn tail to ``_after_spawn``).
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

logger = logging.getLogger(__name__)


# A tracked process handle. Both Popen and the Windows _WinHandle wrapper share
# the .pid / .poll() / .wait() / .terminate() surface used by the base class.
Proc = Any


class BaseAppManager(QObject, ProcessManager, metaclass=ProtocolQtMeta):
    """Shared lifecycle bookkeeping for a multi-app `ProcessManager` adapter.

    Subclasses provide the platform-specific spawn/kill mechanics via the hook
    methods and the `launch` implementation. The base owns the per-idx process
    dict, the lifecycle event emitters, the cross-thread finish hop, and all
    index-keyed queries (is_running / running_pid / swap_indices / ...).
    """

    # Cross-thread bridge: monitor thread -> GUI thread. Carries the Proc itself,
    # not its idx — a tile reorder re-keys _processes mid-flight, so finish and
    # force-kill must resolve the index from process identity at the time the
    # process actually ends.
    _proc_ended = pyqtSignal(object, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._processes: dict[int, Proc] = {}
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

    def swap_indices(self, i: int, j: int) -> None:
        pi = self._processes.pop(i, None)
        pj = self._processes.pop(j, None)
        if pi is not None:
            self._processes[j] = pi
        if pj is not None:
            self._processes[i] = pj

    def remove_index(self, idx: int) -> None:
        self._processes.pop(idx, None)
        self._processes = {
            (k - 1 if k > idx else k): proc
            for k, proc in self._processes.items()
        }

    def is_running(self, idx: int | None = None) -> bool:
        if idx is not None:
            proc = self._processes.get(idx)
            return proc is not None and proc.poll() is None
        return any(p.poll() is None for p in self._processes.values())

    def running_idxs(self) -> list[int]:
        return [i for i, p in self._processes.items() if p.poll() is None]

    def running_pid(self, idx: int) -> int | None:
        if self.is_running(idx):
            return self._processes[idx].pid
        return None

    def all_running_pids(self) -> list[int]:
        return [p.pid for p in self._processes.values() if p.poll() is None]

    def terminate(self, idx: int) -> None:
        if not self.is_running(idx):
            return
        proc = self._processes[idx]
        logger.info("Ending app %d", idx)
        try:
            self._terminate_proc(proc)
            # Bound to *this* proc, not its idx: a reorder or close+relaunch
            # re-keys the dict, so a stale idx-keyed timer would kill the wrong
            # process.
            QTimer.singleShot(3000, lambda: self._force_kill(proc))
        except Exception as e:
            logger.warning("Failed to terminate app %d: %s", idx, e)

    # ── shared pre/post helpers for `launch` ──────────────────────────────────

    def _build_env(self, env: Mapping[str, str] | None) -> dict[str, str]:
        proc_env = os.environ.copy()
        self._prepare_env(proc_env)
        proc_env.update(env or {})
        return proc_env

    def _after_spawn(self, idx: int, proc: Proc) -> bool:
        """Store the spawned process, start its exit monitor, announce start."""
        self._processes[idx] = proc
        threading.Thread(
            target=self._monitor, args=(proc,), daemon=True
        ).start()
        self._started_emitter.emit(AppStarted(idx))
        return True

    def _fail_launch(self, idx: int, command: str, msg: str) -> bool:
        logger.error(msg)
        self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
        return False

    # ── shared monitoring / cleanup ───────────────────────────────────────────

    def _force_kill(self, proc: Proc) -> None:
        # Only kill if this exact process is still tracked and still alive —
        # guards against killing one that already exited or a different one that
        # took its place after a relaunch (and survives a reorder re-keying).
        idx = self._idx_of(proc)
        if idx is not None and proc.poll() is None:
            logger.warning("Force killing app %d", idx)
            try:
                self._force_kill_proc(proc)
            except Exception:
                pass

    def _monitor(self, proc: Proc) -> None:
        self._wait_for_exit(proc)
        self._proc_ended.emit(proc, proc.returncode)

    def _on_finished(self, proc: Proc, exit_code: int) -> None:
        # Resolve the index now, not at launch time: a reorder may have moved
        # this process to a different key in the meantime.
        idx = self._idx_of(proc)
        if idx is None:
            return
        logger.info("Application %d ended (exit code=%d)", idx, exit_code)
        self._processes.pop(idx, None)
        self._finished_emitter.emit(AppFinished(idx))

    def _idx_of(self, proc: Proc) -> int | None:
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