import logging
import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence

from PyQt6.QtCore import QObject

from domain.lifecycle.app_events import AppLaunchFailed
from infrastructure.common.lifecycle.base_app_manager import BaseAppManager

logger = logging.getLogger(__name__)


class AppManager(BaseAppManager):
    """Linux app manager — launches apps as fresh process groups.

    Implements the `ProcessManager` port the app-lifecycle coordinator drives.
    Lifecycle events are exposed as framework-agnostic ``EventEmitter``s (the
    ``on_*`` port methods) rather than ``pyqtSignal``s, so the domain observes
    process state without the Qt machinery leaking through the port.
    """

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

        proc_env = self._build_env(env)

        try:
            proc = subprocess.Popen(
                [command] + arg_list,
                start_new_session=True,   # new session → separate process group
                env=proc_env,
            )
        except FileNotFoundError:
            return self._fail_launch(idx, command, f"Command not found: {command}")
        except PermissionError:
            return self._fail_launch(idx, command, f"Permission denied: {command}")

        return self._after_spawn(idx, proc)

    # ── platform hooks ────────────────────────────────────────────────────────

    def _prepare_env(self, proc_env: dict[str, str]) -> None:
        # Don't leak our layer-shell integration into child apps: it is meant
        # only for KD's own panels/overlays. A Qt child inheriting it would turn
        # its top-level window into a layer-shell surface that respects panel
        # struts (exclusive zone 0) instead of going truly full-screen, leaving
        # cut-off bars top and bottom. Launch apps as ordinary Wayland clients.
        proc_env.pop("QT_WAYLAND_SHELL_INTEGRATION", None)

    def _terminate_proc(self, proc: subprocess.Popen) -> None:
        logger.info("SIGTERM to process group of pid %d", proc.pid)
        self._killpg(proc, signal.SIGTERM)

    def _force_kill_proc(self, proc: subprocess.Popen) -> None:
        logger.warning("Forcing SIGKILL for pid %d", proc.pid)
        self._killpg(proc, signal.SIGKILL)

    def _wait_for_exit(self, proc: subprocess.Popen) -> None:
        # Wait for the leader, then for the whole process group: launchers
        # (Steam, Lutris, …) fork+exec and exit before the real app does.
        # start_new_session=True → pgid == pid of the child process.
        pgid = proc.pid
        proc.wait()
        while True:
            try:
                os.killpg(pgid, 0)   # signal 0 = just check if it exists
            except (ProcessLookupError, PermissionError):
                break
            time.sleep(0.2)

    # ── internal ──────────────────────────────────────────────────────────────

    def _killpg(self, proc: subprocess.Popen, sig: signal.Signals) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("killpg(%s) failed: %s", sig.name, e)
