"""Windows app manager - launches apps via .lnk or .exe."""

import ctypes
import logging
import os
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from ctypes import wintypes
from typing import _ProtocolMeta

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.app_events import AppStarted, AppFinished, AppLaunchFailed
from domain.shared.event_emitter import EventEmitter, Unsubscribe

logger = logging.getLogger(__name__)


class _Meta(type(QObject), _ProtocolMeta):
    """Combined metaclass so a QObject can declare it implements a Protocol port."""

CREATE_NO_WINDOW = 0x08000000
SEE_MASK_NOCLOSEPROCESS = 0x00000040
WAIT_TIMEOUT = 0x00000102


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",        wintypes.DWORD),
        ("fMask",         wintypes.ULONG),
        ("hwnd",          wintypes.HWND),
        ("lpVerb",        wintypes.LPCWSTR),
        ("lpFile",        wintypes.LPCWSTR),
        ("lpParameters",  wintypes.LPCWSTR),
        ("lpDirectory",   wintypes.LPCWSTR),
        ("nShow",         wintypes.INT),
        ("hInstApp",      wintypes.HINSTANCE),
        ("lpIDList",      ctypes.c_void_p),
        ("lpClass",       wintypes.LPCWSTR),
        ("hkeyClass",     wintypes.HKEY),
        ("dwHotKey",      wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess",      wintypes.HANDLE),
    ]


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


class WindowsAppManager(QObject, ProcessManager, metaclass=_Meta):
    """Manages running applications on Windows."""

    _proc_ended = pyqtSignal(object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._processes: dict[int, subprocess.Popen] = {}
        self._started_emitter = EventEmitter[AppStarted]()
        self._finished_emitter = EventEmitter[AppFinished]()
        self._launch_failed_emitter = EventEmitter[AppLaunchFailed]()
        self._proc_ended.connect(self._on_finished)

    def on_started(self, handler: Callable[[AppStarted], None]) -> Unsubscribe:
        return self._started_emitter.subscribe(handler)

    def on_finished(self, handler: Callable[[AppFinished], None]) -> Unsubscribe:
        return self._finished_emitter.subscribe(handler)

    def on_launch_failed(
        self, handler: Callable[[AppLaunchFailed], None]
    ) -> Unsubscribe:
        return self._launch_failed_emitter.subscribe(handler)

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

        proc_env = os.environ.copy()
        proc_env.update(env or {})

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1

        try:
            target = command
            if command.lower().endswith('.lnk'):
                target = self._resolve_lnk(command)
                if target is None:
                    msg = f"Failed to resolve .lnk: {command}"
                    logger.error(msg)
                    self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
                    return False

            if command.startswith("ms-"):
                # Protocol handlers (ms-settings: etc.) can't be tracked via
                # subprocess. Use ShellExecuteEx with SEE_MASK_NOCLOSEPROCESS
                # to obtain the process handle so we can monitor it normally.
                sei = _SHELLEXECUTEINFO()
                sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFO)
                sei.fMask = SEE_MASK_NOCLOSEPROCESS
                sei.lpFile = command
                sei.nShow = 1  # SW_SHOW
                ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
                if ok and sei.hProcess:
                    pid = ctypes.windll.kernel32.GetProcessId(sei.hProcess)
                    proc = _WinHandle(int(sei.hProcess), pid)
                    self._processes[idx] = proc
                    threading.Thread(
                        target=self._monitor, args=(proc,), daemon=True,
                    ).start()
                else:
                    logger.warning("ShellExecuteEx returned no process handle for %s", command)
                self._started_emitter.emit(AppStarted(idx))
                return True
            elif os.path.exists(target):
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
                    except Exception as e:
                        msg = f"Command not found: {command}"
                        logger.error(msg)
                        self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
                        return False
                else:
                    target = found
                    proc = subprocess.Popen(
                        [target] + arg_list,
                        env=proc_env,
                        startupinfo=startupinfo,
                        creationflags=CREATE_NO_WINDOW,
                    )
        except FileNotFoundError as e:
            msg = f"Command not found: {command} - {e}"
            logger.error(msg)
            self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
            return False
        except PermissionError as e:
            msg = f"Permission denied: {command} - {e}"
            logger.error(msg)
            self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
            return False
        except Exception as e:
            msg = f"Failed to launch {command}: {e}"
            logger.error(msg)
            self._launch_failed_emitter.emit(AppLaunchFailed(idx, msg))
            return False

        self._processes[idx] = proc
        threading.Thread(
            target=self._monitor, args=(proc,), daemon=True
        ).start()
        self._started_emitter.emit(AppStarted(idx))
        return True

    def _resolve_lnk(self, lnk_path: str) -> str | None:
        """Resolve a .lnk shortcut to its target path."""
        try:
            import pythoncom
            from win32com.client import Dispatch
            pythoncom.CoInitialize()
            try:
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(lnk_path)
                target = shortcut.Targetpath
                if target:
                    logger.debug("Resolved .lnk %s -> %s", lnk_path, target)
                    return target
            finally:
                pythoncom.CoUninitialize()
        except ImportError:
            logger.warning("pythoncom not available, .lnk resolution skipped")
        except Exception as e:
            logger.warning("Failed to resolve .lnk %s: %s", lnk_path, e)
        return None

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

    def terminate(self, idx: int) -> None:
        if not self.is_running(idx):
            return
        proc = self._processes[idx]
        logger.info("Ending app %d", idx)
        try:
            proc.terminate()
            QTimer.singleShot(3000, lambda: self._force_kill(proc))
        except Exception as e:
            logger.warning("Failed to terminate app %d: %s", idx, e)

    def _force_kill(self, proc: subprocess.Popen) -> None:
        idx = self._idx_of(proc)
        if idx is not None and proc.poll() is None:
            logger.warning("Force killing app %d", idx)
            try:
                proc.kill()
            except Exception:
                pass

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

    def _monitor(self, proc: subprocess.Popen) -> None:
        proc.wait()
        self._proc_ended.emit(proc, proc.returncode)

    def _on_finished(self, proc: subprocess.Popen, exit_code: int) -> None:
        idx = self._idx_of(proc)
        if idx is None:
            return
        logger.info("Application %d ended (exit code=%d)", idx, exit_code)
        self._processes.pop(idx, None)
        self._finished_emitter.emit(AppFinished(idx))

    def _idx_of(self, proc: subprocess.Popen) -> int | None:
        return next((i for i, p in self._processes.items() if p is proc), None)