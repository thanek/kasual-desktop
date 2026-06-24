"""Windows app manager - launches apps via .lnk or .exe."""

import ctypes
import logging
import os
import subprocess
from collections.abc import Mapping, Sequence
from ctypes import wintypes

from domain.lifecycle.app_events import AppStarted
from infrastructure.common.lifecycle.base_app_manager import BaseAppManager, Proc
from infrastructure.windows._win32 import SEE_MASK_NOCLOSEPROCESS, _SHELLEXECUTEINFO

logger = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
WAIT_TIMEOUT = 0x00000102


class _WinHandle:
    """Thin subprocess.Popen-compatible wrapper around a Win32 process HANDLE."""

    def __init__(self, hProcess: int, pid: int) -> None:
        self._h = hProcess
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None or not self._h:
            return self.returncode
        rc = ctypes.windll.kernel32.WaitForSingleObject(self._h, 0)
        if rc != WAIT_TIMEOUT:
            self._read_exit_code()
        return self.returncode

    def wait(self) -> int:
        if self.returncode is None and self._h:
            ctypes.windll.kernel32.WaitForSingleObject(self._h, 0xFFFFFFFF)
            self._read_exit_code()
        return self.returncode or 0

    def terminate(self) -> None:
        if self._h:
            ctypes.windll.kernel32.TerminateProcess(self._h, 1)

    def kill(self) -> None:
        self.terminate()

    def _read_exit_code(self) -> None:
        ec = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(self._h, ctypes.byref(ec))
        self.returncode = ec.value
        ctypes.windll.kernel32.CloseHandle(self._h)
        self._h = None


class WindowsAppManager(BaseAppManager):
    """Manages running applications on Windows."""

    def launch(
        self,
        idx: int,
        command: str,
        args: Sequence[object] = (),
        env: Mapping[str, str] | None = None,
    ) -> bool:
        if self.is_running(idx):
            logger.warning("App %d is already running", idx)
            return False

        arg_list = [str(a) for a in args]
        logger.info("Launching [%d] %s %s", idx, command, arg_list)

        proc_env = self._build_env(env)

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1

        try:
            # Protocol handlers (ms-settings: …) and shortcuts (.lnk) go through the
            # shell: ShellExecuteEx resolves them — no pywin32/.lnk parsing — and for
            # a normal target hands back a trackable process handle. UWP/protocol
            # activations may return no handle; those rely on window-matching.
            if command.startswith("ms-") or command.lower().endswith(".lnk"):
                return self._shell_execute(idx, command)

            target = command
            if os.path.exists(target):
                proc = subprocess.Popen(
                    [target] + arg_list,
                    env=proc_env,
                    startupinfo=startupinfo,
                    creationflags=CREATE_NO_WINDOW,
                )
            else:
                found = self._find_in_path(target)
                if found is None:
                    try:
                        os.startfile(command)
                        self._started_emitter.emit(AppStarted(idx))
                        return True
                    except Exception:
                        return self._fail_launch(idx, command, f"Command not found: {command}")
                else:
                    target = found
                    proc = subprocess.Popen(
                        [target] + arg_list,
                        env=proc_env,
                        startupinfo=startupinfo,
                        creationflags=CREATE_NO_WINDOW,
                    )
        except FileNotFoundError as e:
            return self._fail_launch(idx, command, f"Command not found: {command} - {e}")
        except PermissionError as e:
            return self._fail_launch(idx, command, f"Permission denied: {command} - {e}")
        except Exception as e:
            return self._fail_launch(idx, command, f"Failed to launch {command}: {e}")

        return self._after_spawn(idx, proc)

    def _shell_execute(self, idx: int, command: str) -> bool:
        """Launch a protocol or shortcut via ShellExecuteEx.

        Tracks the spawned process when the shell returns a handle (normal exe
        targets do, thanks to SEE_MASK_NOCLOSEPROCESS); some protocol/UWP
        activations return none and rely on window-matching for running state."""
        sei = _SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFO)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.lpFile = command
        sei.nShow = 1  # SW_SHOW
        ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ok:
            return self._fail_launch(idx, command, f"ShellExecuteEx failed for {command}")
        if sei.hProcess:
            pid = ctypes.windll.kernel32.GetProcessId(sei.hProcess)
            proc = _WinHandle(int(sei.hProcess), pid)
            self._after_spawn(idx, proc)
        else:
            logger.info("No process handle for %s — running tracked via window match", command)
        self._started_emitter.emit(AppStarted(idx))
        return True

    def _find_in_path(self, cmd: str) -> str | None:
        """Find command in PATH."""
        if os.path.isabs(cmd) and os.path.exists(cmd):
            return cmd
        path_dirs = os.environ.get('PATH', '').split(os.pathsep)
        for d in path_dirs:
            candidate = os.path.join(d, cmd)
            if os.path.exists(candidate):
                return candidate
            candidate_ext = candidate + '.exe'
            if os.path.exists(candidate_ext):
                return candidate_ext
        return None

    # ── platform hooks ────────────────────────────────────────────────────────

    def _terminate_proc(self, proc: Proc) -> None:
        proc.terminate()

    def _force_kill_proc(self, proc: Proc) -> None:
        proc.kill()

    def _wait_for_exit(self, proc: Proc) -> None:
        proc.wait()