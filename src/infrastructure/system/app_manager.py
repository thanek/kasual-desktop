import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from typing import _ProtocolMeta  # type: ignore[attr-defined]

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.app_events import AppStarted, AppFinished, AppLaunchFailed
from domain.shared.event_emitter import EventEmitter, Unsubscribe

logger = logging.getLogger(__name__)


class _Meta(type(QObject), _ProtocolMeta):
    """Combined metaclass so a QObject can declare it implements a Protocol port."""


class AppManager(QObject, ProcessManager, metaclass=_Meta):
    """Manages multiple concurrently running applications.

    Implements the `ProcessManager` port the app-lifecycle coordinator drives.
    Lifecycle events are exposed as framework-agnostic ``EventEmitter``s (the
    ``on_*`` port methods) rather than ``pyqtSignal``s, so the domain observes
    process state without the Qt machinery leaking through the port.
    """

    # Internal signal: monitor thread → main Qt thread. Kept as a pyqtSignal
    # because it is the cross-thread marshalling bridge — Qt delivers it queued
    # onto the GUI thread, and only then does the EventEmitter fan out (emit is
    # synchronous in the calling thread, so the hop must happen before it).
    _proc_ended = pyqtSignal(int, int)   # idx, exit_code

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._processes: dict[int, subprocess.Popen] = {}
        self._started_emitter       = EventEmitter[AppStarted]()
        self._finished_emitter      = EventEmitter[AppFinished]()
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

    # ── API ────────────────────────────────────────────────────────────────

    def launch(
        self,
        idx: int,
        command: str,
        args: Sequence[object] = (),
        env: Mapping[str, str] | None = None,
    ) -> bool:
        """Start app *idx*. Returns True if a new process was actually spawned.

        Takes primitive launch parameters (not a domain object) so this process
        adapter stays decoupled from the app model. Returns False when the app is
        already running or the command could not be started (the failure is also
        reported via app_launch_failed). Callers use the return value to decide
        whether to arm post-launch behaviour such as the deferred hide — which
        must not run for a launch that never began.
        """
        if self.is_running(idx):
            logger.warning("App %d is already running — ignoring", idx)
            return False

        arg_list = [str(a) for a in args]
        logger.info("Launching [%d] %s %s", idx, command, arg_list)

        # Don't leak our layer-shell integration into child apps: it is meant
        # only for KD's own panels/overlays. A Qt child inheriting it would turn
        # its top-level window into a layer-shell surface that respects panel
        # struts (exclusive zone 0) instead of going truly full-screen, leaving
        # cut-off bars top and bottom. Launch apps as ordinary Wayland clients.
        proc_env = os.environ.copy()
        proc_env.pop("QT_WAYLAND_SHELL_INTEGRATION", None)
        # Per-app environment overrides (X-Kasual-Env in the .desktop file).
        proc_env.update(env or {})

        try:
            proc = subprocess.Popen(
                [command] + arg_list,
                start_new_session=True,   # new session → separate process group
                env=proc_env,
            )
        except FileNotFoundError:
            msg = f"Command not found: {command}"
            logger.error(msg)
            self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
            return False
        except PermissionError:
            msg = f"Permission denied: {command}"
            logger.error(msg)
            self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
            return False

        self._processes[idx] = proc
        threading.Thread(
            target=self._monitor, args=(idx,), daemon=True
        ).start()
        self._started_emitter.emit(AppStarted(idx))
        return True

    def terminate(self, idx: int) -> None:
        if not self.is_running(idx):
            return
        proc = self._processes[idx]
        logger.info("Ending app %d (SIGTERM)", idx)
        self._killpg(proc, signal.SIGTERM)
        # If the process does not terminate within 3 s — force SIGKILL. Bind the
        # timer to *this* process object, not just idx: a close+relaunch of the
        # same idx within the grace window swaps in a new process, and a stale
        # idx-keyed timer would SIGKILL that freshly launched one.
        QTimer.singleShot(3000, lambda: self._force_kill(idx, proc))

    def is_running(self, idx: int | None = None) -> bool:
        """True if app *idx* is running, or if any app is running when idx is None."""
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
        """PIDs of all currently running application processes."""
        return [p.pid for p in self._processes.values() if p.poll() is None]

    # ── Internal ───────────────────────────────────────────────────────────

    def _killpg(self, proc: subprocess.Popen, sig: signal.Signals) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("killpg(%s) failed: %s", sig.name, e)

    def _force_kill(self, idx: int, proc: subprocess.Popen) -> None:
        # Only kill if this exact process is still the one registered for idx and
        # is still alive — guards against killing a process that already exited or
        # a different one that took idx's place after a relaunch.
        if self._processes.get(idx) is proc and proc.poll() is None:
            logger.warning("Forcing SIGKILL for application %d", idx)
            self._killpg(proc, signal.SIGKILL)

    def _monitor(self, idx: int) -> None:
        """Waits for the process to finish in a background thread, then signals the GUI."""
        proc = self._processes[idx]
        # start_new_session=True → pgid == pid of the child process
        pgid = proc.pid
        proc.wait()
        # Wait until the entire process group exits (handles launchers that fork+exec)
        while True:
            try:
                os.killpg(pgid, 0)   # signal 0 = just check if it exists
            except (ProcessLookupError, PermissionError):
                break
            time.sleep(0.2)
        self._proc_ended.emit(idx, proc.returncode)

    def _on_finished(self, idx: int, exit_code: int) -> None:
        logger.info("Application %d ended (exit code=%d)", idx, exit_code)
        self._processes.pop(idx, None)
        self._finished_emitter.emit(AppFinished(idx))
