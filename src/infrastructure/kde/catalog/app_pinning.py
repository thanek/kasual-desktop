"""Pin an open window as a permanent Kasual app tile — the KDE/freedesktop adapter.

The *Pin to menu* action turns a dynamic open-window tile into a configured app:
it resolves the window's source freedesktop ``.desktop`` entry (the same lookup
the task manager / :mod:`window_icons` uses — by app-id filename or by
``StartupWMClass``), then writes a Kasual app ``.desktop`` into the catalog
directory so the tile persists across restarts.

The placement/unpin mechanics are shared with the Windows adapter via
:class:`AppPinningBase`; only the window→``App`` *source resolution* below is
freedesktop-specific.
"""

import logging
import os
from pathlib import Path

from domain.catalog.app import App
from domain.catalog.window import Window

from infrastructure.common.catalog.pinning_base import AppPinningBase, _strip_desktop_suffix

logger = logging.getLogger(__name__)


class DesktopAppPinning(AppPinningBase):
    def pin(self, window: Window) -> App | None:
        entry = self._source_entry(window.desktop_file, window.resource_class)
        if entry is None:
            logger.warning(
                "Pin: no .desktop for window (desktopFile=%r class=%r)",
                window.desktop_file, window.resource_class,
            )
            return None

        # Carry the window's own class so the pinned tile can be matched back to
        # the running window. KWin's class often differs from the command name
        # (org.kde.konsole vs `konsole`), and many .desktop files omit
        # StartupWMClass — without this the tile would never read as "running" and
        # clicking it would launch a duplicate instead of restoring the window.
        wm_class = window.resource_class or entry.get("StartupWMClass") \
            or _strip_desktop_suffix(window.desktop_file)
        if wm_class:
            entry = {**entry, "StartupWMClass": wm_class}

        try:
            parsed = App.from_desktop_entry(entry)
        except ValueError as exc:
            logger.warning("Pin: unusable .desktop entry: %s", exc)
            return None
        if parsed is None:
            return None
        _, app = parsed

        return self._persist(window, app)

    # ── Source .desktop discovery ────────────────────────────────────────────

    def _source_entry(self, desktop_file: str, resource_class: str) -> dict[str, str] | None:
        """The ``[Desktop Entry]`` mapping of the window's source app, or None."""
        path = self._source_path(desktop_file, resource_class)
        if path is None:
            return None
        entry = self._read_entry(path)
        # A launchable command is the whole point of pinning — reject entries
        # without an Exec (e.g. link/directory entries).
        if entry is None or not entry.get("Exec"):
            return None
        return entry

    def _source_path(self, desktop_file: str, resource_class: str) -> Path | None:
        # 1. Direct filename match: <desktop_file>.desktop or <resource_class>.desktop.
        for name in self._filename_candidates(desktop_file, resource_class):
            for app_dir in _xdg_app_dirs():
                candidate = Path(app_dir) / name
                if candidate.is_file():
                    return candidate
        # 2. StartupWMClass match — how a class such as "signal" maps to
        #    signal-desktop.desktop.
        if resource_class:
            return self._by_startupwmclass(resource_class)
        return None

    @staticmethod
    def _filename_candidates(desktop_file: str, resource_class: str) -> list[str]:
        out: list[str] = []
        if desktop_file:
            out.append(desktop_file if desktop_file.endswith(".desktop")
                       else desktop_file + ".desktop")
        if resource_class and resource_class != desktop_file:
            out.append(resource_class + ".desktop")
        return out

    def _by_startupwmclass(self, resource_class: str) -> Path | None:
        want = resource_class.lower()
        for app_dir in _xdg_app_dirs():
            try:
                names = os.listdir(app_dir)
            except OSError:
                continue
            for filename in names:
                if not filename.endswith(".desktop"):
                    continue
                path = Path(app_dir) / filename
                entry = self._read_entry(path)
                if entry and (entry.get("StartupWMClass") or "").lower() == want:
                    return path
        return None


def _xdg_app_dirs() -> list[str]:
    """The freedesktop ``applications`` directories, user-first (mirrors
    :meth:`window_icons.WindowIconResolver._xdg_app_dirs`)."""
    home   = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    system = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    extra  = [
        "/var/lib/flatpak/exports/share",
        os.path.expanduser("~/.local/share/flatpak/exports/share"),
    ]
    return [os.path.join(d, "applications") for d in [home, *system, *extra]]
