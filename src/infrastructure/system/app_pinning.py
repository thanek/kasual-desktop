"""Pin an open window as a permanent Kasual app tile — the :class:`AppPinning` adapter.

The *Pin to menu* action turns a dynamic open-window tile into a configured app:
it resolves the window's source freedesktop ``.desktop`` entry (the same lookup
the task manager / :mod:`window_icons` uses — by app-id filename or by
``StartupWMClass``), then writes a Kasual app ``.desktop`` into the catalog
directory so the tile persists across restarts.

Infrastructure: the freedesktop discovery (XDG dirs, ``configparser``) and the
file write live here; the App↔``.desktop`` mapping is the domain's
(:meth:`App.from_desktop_entry` / :meth:`App.to_desktop_entry`).
"""

import configparser
import logging
import os
import re
from pathlib import Path

from domain.catalog.app import App
from domain.catalog.window import Window
from domain.menu.ports import AppPinning

from .app_config import apps_dir, _ordered_desktop_paths, _write_desktop

logger = logging.getLogger(__name__)


class DesktopAppPinning(AppPinning):
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

        directory = apps_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Pin: cannot create apps dir %s: %s", directory, exc)
            return None

        order = self._next_order(directory)
        path = self._unique_path(directory, window, app)
        try:
            _write_desktop(path, app.to_desktop_entry(order))
        except OSError as exc:
            logger.error("Pin: cannot write %s: %s", path, exc)
            return None

        logger.info("Pinned %r to %s", app.name, path.name)
        return app

    def unpin(self, index: int) -> None:
        ordered = _ordered_desktop_paths()
        if not (0 <= index < len(ordered)):
            logger.warning("Unpin out of range: %d of %d", index, len(ordered))
            return
        path = ordered[index]
        try:
            path.unlink()
            logger.info("Unpinned %s", path.name)
        except OSError as exc:
            logger.error("Unpin: cannot delete %s: %s", path, exc)

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

    @staticmethod
    def _read_entry(path: Path) -> dict[str, str] | None:
        try:
            cp = configparser.RawConfigParser()
            cp.optionxform = str
            cp.read(path, encoding="utf-8")
            if not cp.has_section("Desktop Entry"):
                return None
            return dict(cp["Desktop Entry"])
        except Exception:
            return None

    # ── Placement / filename ─────────────────────────────────────────────────

    def _next_order(self, directory: Path) -> int:
        """One past the highest existing ``X-Kasual-Order`` so the pinned tile sorts
        last. Uses the max (not the count) so a gap left by a prior unpin cannot
        collide with an existing order and reshuffle the on-disk vs. live index."""
        orders = [
            int(value)
            for path in directory.glob("*.desktop")
            for value in [(self._read_entry(path) or {}).get("X-Kasual-Order")]
            if value is not None and value.lstrip("-").isdigit()
        ]
        return max(orders, default=-1) + 1

    def _unique_path(self, directory: Path, window: Window, app: App) -> Path:
        base = _slugify(window.resource_class or window.desktop_file or app.name) or "app"
        path = directory / f"{base}.desktop"
        i = 2
        while path.exists():
            path = directory / f"{base}-{i}.desktop"
            i += 1
        return path


_SLUG_STRIP = re.compile(r"[^a-z0-9._-]+")


def _strip_desktop_suffix(name: str) -> str:
    """Drop a trailing ``.desktop`` (but keep dotted app-ids like org.kde.konsole)."""
    return name[: -len(".desktop")] if name.endswith(".desktop") else name


def _slugify(text: str) -> str:
    """A filesystem-safe lowercase slug for the ``.desktop`` filename.

    Keeps inner dots so a reverse-DNS app-id stays intact (``org.kde.konsole`` →
    ``org.kde.konsole.desktop``); only a trailing ``.desktop`` is stripped.
    """
    text = _strip_desktop_suffix(text.strip().lower())
    return _SLUG_STRIP.sub("-", text).strip("-")


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
