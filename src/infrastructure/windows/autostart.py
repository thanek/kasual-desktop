"""Autostart through the current user's ``Run`` registry key."""

import logging
import subprocess
import sys
import winreg
from pathlib import Path

from domain.system.autostart import Autostart

logger = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_TASK_MANAGER_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run")
_VALUE_NAME = "Kasual Desktop"


class WindowsAutostart(Autostart):
    def __init__(self, command: str) -> None:
        self._command = command

    def is_enabled(self) -> bool:
        return _read(_RUN_KEY) is not None and not _switched_off_in_task_manager()

    def set_enabled(self, enabled: bool) -> None:
        try:
            if enabled:
                _write(_RUN_KEY, self._command)
                _delete(_TASK_MANAGER_KEY)
            else:
                _delete(_RUN_KEY)
        except OSError as exc:
            logger.error("Cannot change autostart in the registry: %s", exc)


def command_running(script: Path) -> str:
    return subprocess.list2cmdline([_interpreter_without_console(), str(script)])


def _interpreter_without_console() -> str:
    windowed = Path(sys.executable).with_name("pythonw.exe")
    return str(windowed) if windowed.exists() else sys.executable


def _switched_off_in_task_manager() -> bool:
    state = _read(_TASK_MANAGER_KEY)
    return bool(state) and _is_odd(state[0])


def _is_odd(number: int) -> bool:
    return number % 2 == 1


def _read(key_path: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, _VALUE_NAME)[0]
    except OSError:
        return None


def _write(key_path: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, value)


def _delete(key_path: str) -> None:
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass
