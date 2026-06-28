"""List installed freedesktop apps as add-app candidates — the Linux scanner.

The source behind the ``[＋]`` tile on Linux (an :class:`InstalledApps`): it walks
the XDG ``applications`` directories (same set as the icon/pin lookups), parses
each ``.desktop`` with the domain's freedesktop rules, and offers every visible
application tile as a :class:`CandidateApp`. The add-app use-case filters out the
already-pinned ones; the picker filters by name. Pure scanning — the file I/O is
here, the ``[Desktop Entry]`` → :class:`App` rules stay in the domain.
"""

import configparser
import logging
import os
from pathlib import Path

from domain.catalog.app import App, ORDER_DEFAULT
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import InstalledApps

from infrastructure.linux.catalog.app_pinning import _xdg_app_dirs

logger = logging.getLogger(__name__)


def _current_desktops() -> set[str]:
    """The running desktop environments (``$XDG_CURRENT_DESKTOP``, colon-list)."""
    return {d for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d}


def _entry_list(value: str | None) -> set[str]:
    """Parse a freedesktop semicolon list (e.g. ``OnlyShowIn``) into a set."""
    return {p for p in (value or "").split(";") if p}


def _hidden_in_this_desktop(entry: dict[str, str]) -> bool:
    """Honor freedesktop ``OnlyShowIn``/``NotShowIn`` for the current desktop.

    A huge share of a system's ``.desktop`` files are other desktops' control
    panels (GNOME/Cinnamon/LXQt settings) that declare where they belong; without
    this the add-app list fills with config modules that don't apply here."""
    here = _current_desktops()
    only = _entry_list(entry.get("OnlyShowIn"))
    if only and not (here & only):
        return True
    return bool(here & _entry_list(entry.get("NotShowIn")))


class XdgInstalledApps(InstalledApps):
    """Scan the XDG ``applications`` dirs for installable app tiles."""

    def scan(self) -> list[CandidateApp]:
        # User dirs come first (see _xdg_app_dirs), so the first entry seen for a
        # given .desktop filename wins — a user override shadows the system copy.
        by_key: dict[str, CandidateApp] = {}
        for app_dir in _xdg_app_dirs():
            for path in sorted(Path(app_dir).glob("**/*.desktop")):
                key = path.stem
                if key in by_key:
                    continue
                candidate = self._candidate(path, key)
                if candidate is not None:
                    by_key[key] = candidate
        candidates = sorted(by_key.values(), key=lambda c: c.app.name.casefold())
        logger.info("Scanned %d installed app(s)", len(candidates))
        return candidates

    def _candidate(self, path: Path, key: str) -> CandidateApp | None:
        """Parse one ``.desktop`` into an add-app candidate, or None to skip it.

        Skips non-tiles (``NoDisplay``/``Hidden``/non-Application — the domain
        returns None) and malformed entries (no usable Name/Exec — it raises).
        Never pre-selected: the user picks what to add."""
        entry = self._read_entry(path)
        if entry is None or _hidden_in_this_desktop(entry):
            return None
        try:
            parsed = App.from_desktop_entry(entry)
        except ValueError:
            return None
        if parsed is None:
            return None
        _, app = parsed
        return CandidateApp(key=key, app=app, order=ORDER_DEFAULT, default_selected=False)

    @staticmethod
    def _read_entry(path: Path) -> dict[str, str] | None:
        """The ``[Desktop Entry]`` mapping of *path* (mirrors app_config parsing)."""
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str   # .desktop keys are case-sensitive
        try:
            parser.read(path, encoding="utf-8")
        except (OSError, configparser.Error):
            return None
        if not parser.has_section("Desktop Entry"):
            return None
        return dict(parser["Desktop Entry"])
