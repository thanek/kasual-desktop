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

from domain.catalog.app import App
from domain.catalog.catalog import AppCatalog

logger = logging.getLogger(__name__)


def apps_dir() -> Path:
    """Directory holding the app ``.desktop`` files."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "kasual-desktop" / "apps"


def load_apps() -> AppCatalog:
    """Return the :class:`AppCatalog` built from the ``.desktop`` files in :func:`apps_dir`.

    This adapter does the I/O — find and parse the files into ``(order, source,
    App)`` entries — and hands them to :meth:`AppCatalog.from_entries`, which owns
    the placement rule. Malformed or hidden entries are skipped; one bad file
    never aborts the whole load. The directory is created if missing so the user
    has a place to drop files.
    """
    directory = apps_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create apps dir %s: %s", directory, exc)
        return AppCatalog()

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

    catalog = AppCatalog.from_entries(entries)
    logger.info("Loaded %d app(s)", len(catalog))
    return catalog


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
