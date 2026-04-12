"""Resolving application icons and names based on .desktop files (XDG)."""

import configparser
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


def _xdg_app_dirs() -> list[str]:
    home   = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    system = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')
    extra  = [
        '/var/lib/flatpak/exports/share',
        os.path.expanduser('~/.local/share/flatpak/exports/share'),
    ]
    return [os.path.join(d, 'applications') for d in [home] + system + extra]


def _icon_name_from_desktop(path: str) -> str | None:
    try:
        cp = configparser.RawConfigParser()
        cp.read(path, encoding='utf-8')
        return cp.get('Desktop Entry', 'Icon', fallback=None)
    except Exception:
        return None


@lru_cache(maxsize=128)
def _resolve_window_meta(
    desktop_file: str, resource_class: str
) -> tuple[str | None, str | None]:
    """
    Finds the first matching .desktop file and returns (name, icon_name).
    Both fields are read in a single pass — the result is cached.
    """
    candidates: list[str] = []
    if desktop_file:
        candidates.append(desktop_file if desktop_file.endswith('.desktop')
                          else desktop_file + '.desktop')
    if resource_class and resource_class != desktop_file:
        candidates.append(resource_class + '.desktop')

    for apps_dir in _xdg_app_dirs():
        for filename in candidates:
            path = os.path.join(apps_dir, filename)
            if os.path.isfile(path):
                try:
                    cp = configparser.RawConfigParser()
                    cp.read(path, encoding='utf-8')
                    name      = cp.get('Desktop Entry', 'Name', fallback=None) or None
                    icon_name = cp.get('Desktop Entry', 'Icon', fallback=None) or None
                    return name, icon_name
                except Exception:
                    pass
    return None, None


def resolve_window_name(desktop_file: str, resource_class: str) -> str | None:
    """Returns the official application name (Name=) from the .desktop file, or None."""
    return _resolve_window_meta(desktop_file, resource_class)[0]


def resolve_window_icon(desktop_file: str, resource_class: str):
    """Returns QIcon for a KWin window, or None. Result is cached by _resolve_window_meta."""
    from PyQt6.QtGui import QIcon

    _, icon_name = _resolve_window_meta(desktop_file, resource_class)

    # Fallback: try resource class as a theme icon name
    if not icon_name:
        icon_name = resource_class or desktop_file

    if not icon_name:
        return None

    if os.path.isabs(icon_name):
        icon = QIcon(icon_name)
        return icon if not icon.isNull() else None

    icon = QIcon.fromTheme(icon_name)
    return icon if not icon.isNull() else None
