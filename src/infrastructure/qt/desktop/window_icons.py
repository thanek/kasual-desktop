"""Resolving application icons and names for open windows.

Mirrors how the KWin/Plasma task manager finds an icon for a window, layered
from most to least authoritative:

  1. The window's .desktop entry — matched by desktop-file id, by
     ``StartupWMClass`` (KService's main hook), or by ``<class>.desktop`` name.
  2. Icon-theme name transforms derived from the window class — handles the
     common app-id/icon-name mismatches (``jetbrains-clion`` → ``clion``,
     ``steam_app_<id>`` → ``steam_icon_<id>``).
  3. The window's embedded ``_NET_WM_ICON`` pixmap (XWayland only) — the last
     resort for apps with no theme/.desktop entry at all, e.g. Steam games.
"""

import configparser
import logging
import os

logger = logging.getLogger(__name__)

# Embedded _NET_WM_ICON pixmaps are often tiny (Steam games ship a 32px icon).
# QIcon will not upscale a single small pixmap, so QToolButton renders it
# centred and looking lost on a large tile. Smoothly pre-scale small embedded
# icons up to this size so the tile fills — same trade-off KWin's task manager
# makes (a soft but correctly-sized icon beats a sharp tiny one).
_EMBEDDED_ICON_TARGET = 256


def theme_icon_candidates(resource_class: str, desktop_file: str) -> list[str]:
    """Ordered, de-duplicated icon-theme names to try for a window class.

    Pure function (no Qt) so it is cheap to unit-test. The caller picks the
    first name for which the icon theme actually has an entry.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if not name:
            return
        name = name.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    for base in (resource_class, desktop_file):
        if not base:
            continue
        base = base.strip()
        # Steam installs per-game icons as steam_icon_<appid> in hicolor.
        if base.startswith("steam_app_"):
            add("steam_icon_" + base[len("steam_app_"):])
        add(base)
        # Vendor prefixes that never appear in the themed icon name.
        for prefix in ("jetbrains-",):
            if base.startswith(prefix):
                add(base[len(prefix):])
        # Last segment of a dotted/dashed class (org.kde.elisa → elisa).
        if "-" in base:
            add(base.rsplit("-", 1)[-1])
        if "." in base:
            add(base.rsplit(".", 1)[-1])
        add(base.lower())

    return out


class WindowIconResolver:
    """Resolves window names and icons. Results are cached per instance."""

    def __init__(self) -> None:
        self._meta_cache: dict[tuple[str, str], tuple[str | None, str | None]] = {}
        self._icon_cache: dict[tuple[str, str, int], object] = {}
        self._swc_index: dict[str, tuple[str | None, str | None]] | None = None
        self._x11_reader = None

    # ── Names ───────────────────────────────────────────────────────────────

    def resolve_name(self, desktop_file: str, resource_class: str) -> str | None:
        """Returns the application name (Name=) from the .desktop file, or None."""
        return self._meta(desktop_file, resource_class)[0]

    # ── Icons ───────────────────────────────────────────────────────────────

    def resolve_icon(self, desktop_file: str, resource_class: str, pid: int = 0):
        """Return a QIcon for the window, or None if nothing could be resolved."""
        key = (desktop_file, resource_class, pid)
        if key in self._icon_cache:
            return self._icon_cache[key]
        icon = self._resolve_icon_uncached(desktop_file, resource_class, pid)
        self._icon_cache[key] = icon
        return icon

    def _resolve_icon_uncached(self, desktop_file: str, resource_class: str, pid: int):
        from PyQt6.QtGui import QIcon

        # 1. Icon name declared by the matched .desktop entry.
        _, icon_name = self._meta(desktop_file, resource_class)
        if icon_name:
            icon = self._icon_from_name(icon_name)
            if icon is not None:
                return icon

        # 2. Icon-theme name transforms derived from the window class.
        for cand in theme_icon_candidates(resource_class, desktop_file):
            if QIcon.hasThemeIcon(cand):
                return QIcon.fromTheme(cand)

        # 3. Embedded _NET_WM_ICON pixmap (XWayland apps with no theme entry).
        if pid:
            image = self._x11().read_icon(pid, resource_class)
            if image is not None and not image.isNull():
                return self._icon_from_image(image)

        # 4. Windows: the process executable's shell icon, by PID.
        if pid:
            icon = _windows_pid_icon(pid)
            if icon is not None:
                return icon

        return None

    @staticmethod
    def _icon_from_image(image):
        """Build a QIcon from a raw embedded image, upscaling small ones smoothly."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QIcon, QPixmap

        if max(image.width(), image.height()) < _EMBEDDED_ICON_TARGET:
            image = image.scaled(
                _EMBEDDED_ICON_TARGET, _EMBEDDED_ICON_TARGET,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return QIcon(QPixmap.fromImage(image))

    @staticmethod
    def _icon_from_name(icon_name: str):
        from PyQt6.QtGui import QIcon

        if os.path.isabs(icon_name):
            icon = QIcon(icon_name)
            return icon if not icon.isNull() else None
        if QIcon.hasThemeIcon(icon_name):
            return QIcon.fromTheme(icon_name)
        return None

    def _x11(self):
        if self._x11_reader is None:
            from .x11_icon import X11IconReader
            self._x11_reader = X11IconReader()
        return self._x11_reader

    # ── .desktop lookup ──────────────────────────────────────────────────────

    def _meta(self, desktop_file: str, resource_class: str) -> tuple[str | None, str | None]:
        key = (desktop_file, resource_class)
        if key not in self._meta_cache:
            self._meta_cache[key] = self._lookup(desktop_file, resource_class)
        return self._meta_cache[key]

    def _lookup(self, desktop_file: str, resource_class: str) -> tuple[str | None, str | None]:
        # 1. Direct filename match: <desktop_file>.desktop or <resource_class>.desktop.
        entry = self._lookup_by_filename(desktop_file, resource_class)
        if entry != (None, None):
            return entry

        # 2. StartupWMClass match — how KService maps a window class such as
        #    "signal" to signal-desktop.desktop.
        if resource_class:
            hit = self._startupwmclass_index().get(resource_class.lower())
            if hit is not None:
                return hit

        return None, None

    def _lookup_by_filename(self, desktop_file: str, resource_class: str) -> tuple[str | None, str | None]:
        candidates: list[str] = []
        if desktop_file:
            candidates.append(desktop_file if desktop_file.endswith('.desktop')
                              else desktop_file + '.desktop')
        if resource_class and resource_class != desktop_file:
            candidates.append(resource_class + '.desktop')

        for apps_dir in self._xdg_app_dirs():
            for filename in candidates:
                path = os.path.join(apps_dir, filename)
                if os.path.isfile(path):
                    meta = self._parse_desktop(path)
                    if meta != (None, None):
                        return meta
        return None, None

    def _startupwmclass_index(self) -> dict[str, tuple[str | None, str | None]]:
        """Lazily build {StartupWMClass.lower(): (Name, Icon)} over all .desktop files."""
        if self._swc_index is not None:
            return self._swc_index
        index: dict[str, tuple[str | None, str | None]] = {}
        for apps_dir in self._xdg_app_dirs():
            try:
                names = os.listdir(apps_dir)
            except OSError:
                continue
            for filename in names:
                if not filename.endswith('.desktop'):
                    continue
                path = os.path.join(apps_dir, filename)
                swc = self._parse_startupwmclass(path)
                if swc:
                    key = swc.lower()
                    # First match wins — earlier dirs (user) take precedence.
                    index.setdefault(key, self._parse_desktop(path))
        self._swc_index = index
        return index

    @staticmethod
    def _parse_desktop(path: str) -> tuple[str | None, str | None]:
        try:
            cp = configparser.RawConfigParser()
            cp.read(path, encoding='utf-8')
            name      = cp.get('Desktop Entry', 'Name', fallback=None) or None
            icon_name = cp.get('Desktop Entry', 'Icon', fallback=None) or None
            return name, icon_name
        except Exception:
            return None, None

    @staticmethod
    def _parse_startupwmclass(path: str) -> str | None:
        try:
            cp = configparser.RawConfigParser()
            cp.read(path, encoding='utf-8')
            return cp.get('Desktop Entry', 'StartupWMClass', fallback=None) or None
        except Exception:
            return None

    @staticmethod
    def _xdg_app_dirs() -> list[str]:
        home   = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        system = os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')
        extra  = [
            '/var/lib/flatpak/exports/share',
            os.path.expanduser('~/.local/share/flatpak/exports/share'),
        ]
        return [os.path.join(d, 'applications') for d in [home] + system + extra]


def _windows_pid_icon(pid: int):
    """A dynamic window's icon on Windows: the shell (jumbo) icon of the process's
    executable, resolved from its PID. No-op off Windows."""
    if os.name != 'nt' or not pid:
        return None
    from infrastructure.windows.window_manager import _get_exe_path
    from infrastructure.qt.icons import shell_icon
    exe = _get_exe_path(pid)
    return shell_icon(exe) if exe else None
