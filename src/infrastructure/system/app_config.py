"""Load Kasual app definitions from freedesktop ``.desktop`` files.

Apps live in ``$XDG_CONFIG_HOME/kasual-desktop/apps/*.desktop`` (defaulting to
``~/.config/...``). This module is the *adapter*: it finds the files, parses the
INI bytes with ``configparser`` and feeds raw ``[Desktop Entry]`` mappings to
:meth:`domain.app.App.from_desktop_entry`, which owns the freedesktop→App rules.

Intentionally Qt-free: ``load_apps()`` runs before the ``QApplication`` exists
(see ``main.py``), so themed-icon resolution is deferred to the TileBar.
"""

import configparser
import logging
import os
from pathlib import Path

from domain.app import App

logger = logging.getLogger(__name__)


def apps_dir() -> Path:
    """Directory holding the app ``.desktop`` files."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "kasual-desktop" / "apps"


def load_apps() -> list[App]:
    """Return the ordered list of :class:`App` definitions found in :func:`apps_dir`.

    Malformed or hidden entries are skipped; one bad file never aborts the whole
    load. The directory is created if missing so the user has a place to drop files.
    """
    directory = apps_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create apps dir %s: %s", directory, exc)
        return []

    logger.info("Loading apps from %s", directory)
    entries: list[tuple[int, str, App]] = []
    for path in directory.glob("*.desktop"):
        try:
            parsed = _parse_desktop(path)
        except Exception as exc:
            logger.warning("Skipping %s: %s", path.name, exc)
            continue
        if parsed is None:
            continue
        order, app = parsed
        entries.append((order, path.name, app))

    entries.sort(key=lambda e: (e[0], e[1]))
    apps = [app for _, _, app in entries]
    logger.info("Loaded %d app(s)", len(apps))
    return apps


def _parse_desktop(path: Path) -> "tuple[int, App] | None":
    """Read one ``.desktop`` file and hand its ``[Desktop Entry]`` to the domain.

    The configparser mechanics live here; the mapping rules live in the domain
    factory. Returns its ``(order, app) | None``; may raise on a malformed entry.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # .desktop keys are case-sensitive
    parser.read(path, encoding="utf-8")

    if not parser.has_section("Desktop Entry"):
        return None
    return App.from_desktop_entry(dict(parser["Desktop Entry"]))
