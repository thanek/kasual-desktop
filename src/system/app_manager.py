import logging
import os
import signal
import subprocess
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class AppManager(QObject):
    """Manages a single running application."""

    app_started  = pyqtSignal(int)   # idx
    app_finished = pyqtSignal(int)   # idx

    # Internal signal: monitor thread → main Qt thread
    _proc_ended = pyqtSignal(int, int)   # idx, exit_code

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._running_idx: int | None = None
        self._proc_ended.connect(self._on_finished)

    # ── API ────────────────────────────────────────────────────────────────

    def launch(self, idx: int, app: dict) -> None:
        if self._process is not None and self._process.poll() is None:
            logger.warning(
                "Attempt to launch app %d when %d is already running – ignoring",
                idx, self._running_idx,
            )
            return

        command = app["command"]
        args    = [str(a) for a in app.get("args", [])]
        logger.info("Launching [%d] %s %s", idx, command, args)

        self._process = subprocess.Popen(
            [command] + args,
            start_new_session=True,   # new session → separate process group
        )
        self._running_idx = idx
        threading.Thread(
            target=self._monitor, args=(idx,), daemon=True
        ).start()
        self.app_started.emit(idx)

    def terminate(self) -> None:
        if self._process is not None and self._process.poll() is None:
            logger.info("Ending app %d (SIGTERM)", self._running_idx)
            self._killpg(signal.SIGTERM)
            # If the process does not terminate within 3 s — force SIGKILL
            QTimer.singleShot(3000, self._force_kill)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def running_idx(self) -> int | None:
        return self._running_idx if self.is_running() else None

    def running_pid(self) -> int | None:
        if self._process is not None and self._process.poll() is None:
            return self._process.pid
        return None

    # ── Internal ───────────────────────────────────────────────────────────

    def _killpg(self, sig: signal.Signals) -> None:
        if self._process is None:
            return
        try:
            os.killpg(os.getpgid(self._process.pid), sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("killpg(%s) failed: %s", sig.name, e)

    def _force_kill(self) -> None:
        if self._process is not None and self._process.poll() is None:
            logger.warning("Forcing SIGKILL for application %d", self._running_idx)
            self._killpg(signal.SIGKILL)

    def _monitor(self, idx: int) -> None:
        """Waits for the process to finish in a background thread, then signals the GUI."""
        # start_new_session=True → pgid == pid of the child process
        pgid = self._process.pid
        self._process.wait()
        # Wait until the entire process group exits (handles launchers that fork+exec)
        while True:
            try:
                os.killpg(pgid, 0)   # signal 0 = just check if it exists
            except (ProcessLookupError, PermissionError):
                break
            time.sleep(0.5)
        self._proc_ended.emit(idx, self._process.returncode)

    def _on_finished(self, idx: int, exit_code: int) -> None:
        logger.info("Application %d ended (exit code=%d)", idx, exit_code)
        self._running_idx = None
        self._process     = None
        self.app_finished.emit(idx)
