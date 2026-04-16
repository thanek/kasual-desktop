import logging
import os
import signal
import subprocess
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class AppManager(QObject):
    """Manages multiple concurrently running applications."""

    app_started       = pyqtSignal(int)        # idx
    app_finished      = pyqtSignal(int)        # idx
    app_launch_failed = pyqtSignal(int, str)   # idx, error message

    # Internal signal: monitor thread → main Qt thread
    _proc_ended = pyqtSignal(int, int)   # idx, exit_code

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._processes: dict[int, subprocess.Popen] = {}
        self._proc_ended.connect(self._on_finished)

    # ── API ────────────────────────────────────────────────────────────────

    def launch(self, idx: int, app: dict) -> None:
        if self.is_running(idx):
            logger.warning("App %d is already running — ignoring", idx)
            return

        command = app["command"]
        args    = [str(a) for a in app.get("args", [])]
        logger.info("Launching [%d] %s %s", idx, command, args)

        try:
            proc = subprocess.Popen(
                [command] + args,
                start_new_session=True,   # new session → separate process group
            )
        except FileNotFoundError:
            msg = f"Command not found: {command}"
            logger.error(msg)
            self.app_launch_failed.emit(idx, msg)
            return
        except PermissionError:
            msg = f"Permission denied: {command}"
            logger.error(msg)
            self.app_launch_failed.emit(idx, msg)
            return

        self._processes[idx] = proc
        threading.Thread(
            target=self._monitor, args=(idx,), daemon=True
        ).start()
        self.app_started.emit(idx)

    def terminate(self, idx: int) -> None:
        if not self.is_running(idx):
            return
        logger.info("Ending app %d (SIGTERM)", idx)
        self._killpg(idx, signal.SIGTERM)
        # If the process does not terminate within 3 s — force SIGKILL
        QTimer.singleShot(3000, lambda: self._force_kill(idx))

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

    def _killpg(self, idx: int, sig: signal.Signals) -> None:
        proc = self._processes.get(idx)
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("killpg(%s) failed: %s", sig.name, e)

    def _force_kill(self, idx: int) -> None:
        if self.is_running(idx):
            logger.warning("Forcing SIGKILL for application %d", idx)
            self._killpg(idx, signal.SIGKILL)

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
            time.sleep(0.5)
        self._proc_ended.emit(idx, proc.returncode)

    def _on_finished(self, idx: int, exit_code: int) -> None:
        logger.info("Application %d ended (exit code=%d)", idx, exit_code)
        self._processes.pop(idx, None)
        self.app_finished.emit(idx)
