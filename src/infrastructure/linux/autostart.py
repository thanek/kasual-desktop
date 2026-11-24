"""Autostart through the freedesktop (XDG) autostart directory."""

import configparser
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from domain.system.autostart import Autostart

logger = logging.getLogger(__name__)

_ENTRY_NAME = "kasual-desktop.desktop"
_PACKAGED_LAUNCHER = "kasual-desktop"
_CHECKOUT_LAUNCHER = "kasual.sh"
_SECTION = "Desktop Entry"

_SYSTEMD_RUNS_ENTRIES = (
    "systemctl", "--user", "is-active", "--quiet", "xdg-desktop-autostart.target")
_LXSESSION_RUNS_ENTRIES = "lxsession-xdg-autostart"
_GIVE_UP_AFTER_S = 5

_NEEDS_NO_QUOTING = re.compile(r"[A-Za-z0-9_./-]+")
_ESCAPED_INSIDE_QUOTES = re.compile(r'(["`$\\])')


class XdgAutostart(Autostart):
    def __init__(self, launcher: str) -> None:
        self._launcher = launcher

    def is_enabled(self) -> bool:
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            if not parser.read(_entry_path(), encoding="utf-8"):
                return False
            hidden = parser.getboolean(_SECTION, "Hidden", fallback=False)
            enabled_on_gnome = parser.getboolean(
                _SECTION, "X-GNOME-Autostart-enabled", fallback=True)
        except (OSError, ValueError, configparser.Error) as exc:
            logger.warning("Cannot read %s: %s", _entry_path(), exc)
            return False
        return parser.has_section(_SECTION) and enabled_on_gnome and not hidden

    def set_enabled(self, enabled: bool) -> None:
        try:
            if enabled:
                self._write_entry()
            else:
                _entry_path().unlink(missing_ok=True)
        except OSError as exc:
            logger.error("Cannot change autostart in %s: %s", _entry_path(), exc)

    def _write_entry(self) -> None:
        path = _entry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"[{_SECTION}]\n"
            "Type=Application\n"
            "Name=Kasual Desktop\n"
            f"Exec={_as_exec_argument(self._launcher)}\n"
            f"TryExec={_as_string_value(self._launcher)}\n"
            "Icon=kasual-desktop\n"
            "Terminal=false\n",
            encoding="utf-8",
        )


def launcher_for(install_root: Path) -> str:
    checkout_launcher = install_root / _CHECKOUT_LAUNCHER
    return str(checkout_launcher) if checkout_launcher.exists() else _PACKAGED_LAUNCHER


def systemd_runs_autostart_entries() -> bool:
    try:
        return subprocess.run(
            _SYSTEMD_RUNS_ENTRIES, timeout=_GIVE_UP_AFTER_S).returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Cannot ask systemd about autostart: %s", exc)
        return False


def lxsession_runs_autostart_entries() -> bool:
    return shutil.which(_LXSESSION_RUNS_ENTRIES) is not None


def _entry_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "autostart" / _ENTRY_NAME


def _as_exec_argument(path: str) -> str:
    if _NEEDS_NO_QUOTING.fullmatch(path):
        return path
    quoted = _ESCAPED_INSIDE_QUOTES.sub(r"\\\1", path).replace("%", "%%")
    return _as_string_value(f'"{quoted}"')


def _as_string_value(text: str) -> str:
    return text.replace("\\", "\\\\")
