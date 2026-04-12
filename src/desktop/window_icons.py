"""Resolwowanie ikon i nazw aplikacji na podstawie plików .desktop (XDG)."""

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
    Szuka pierwszego pasującego pliku .desktop i zwraca (name, icon_name).
    Oba pola są odczytywane w jednym przebiegu — wynik jest cache'owany.
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
    """Zwraca oficjalną nazwę aplikacji (Name=) z pliku .desktop lub None."""
    return _resolve_window_meta(desktop_file, resource_class)[0]


def resolve_window_icon(desktop_file: str, resource_class: str):
    """Zwraca QIcon dla okna KWin lub None. Wynik jest cache'owany przez _resolve_window_meta."""
    from PyQt6.QtGui import QIcon

    _, icon_name = _resolve_window_meta(desktop_file, resource_class)

    # Fallback: spróbuj klasy zasobu jako nazwy ikony motywu
    if not icon_name:
        icon_name = resource_class or desktop_file

    if not icon_name:
        return None

    if os.path.isabs(icon_name):
        icon = QIcon(icon_name)
        return icon if not icon.isNull() else None

    icon = QIcon.fromTheme(icon_name)
    return icon if not icon.isNull() else None
