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
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import AppProvisioning

logger = logging.getLogger(__name__)


def config_root() -> Path:
    """Kasual Desktop's config directory (``$XDG_CONFIG_HOME/kasual-desktop``)."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "kasual-desktop"


def apps_dir() -> Path:
    """Directory holding the app ``.desktop`` files."""
    return config_root() / "apps"


def provisioned_marker() -> Path:
    """The first-run provisioning marker (``<config>/.provisioned``)."""
    return config_root() / ".provisioned"


def load_apps() -> AppCatalog:
    """Return the :class:`AppCatalog` built from the ``.desktop`` files in :func:`apps_dir`.

    This adapter does the I/O — find and parse the files into ``(order, source,
    App)`` entries — and hands them to :meth:`AppCatalog.from_entries`, which owns
    the placement rule. Malformed or hidden entries are skipped; one bad file
    never aborts the whole load. A missing directory yields an empty catalog —
    creating it is provisioning's job (see :class:`DesktopAppProvisioning`), so
    directory-existence is no longer a side effect of loading.
    """
    directory = apps_dir()
    if not directory.is_dir():
        logger.info("Apps dir %s missing — empty catalog", directory)
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


class DesktopAppProvisioning(AppProvisioning):
    """Seed the user's app catalog by writing ``.desktop`` files + a marker.

    The write side of the app-loading seam: just as :func:`load_apps` reads the
    files and hands raw mappings to the domain, this takes the domain's
    :meth:`App.to_desktop_entry` mapping and does the ``configparser`` I/O. The
    marker (``<config>/.provisioned``) records that first-run happened, so it is
    keyed on intent — not on whether any apps were actually written.
    """

    def is_provisioned(self) -> bool:
        return provisioned_marker().exists()

    def provision(self, candidates: list[CandidateApp]) -> None:
        directory = apps_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Cannot create apps dir %s: %s", directory, exc)
            return

        for candidate in candidates:
            path = directory / f"{candidate.key}.desktop"
            try:
                _write_desktop(path, candidate.app.to_desktop_entry(candidate.order))
            except OSError as exc:
                # One failed write must not abort the rest (mirrors load_apps).
                logger.error("Cannot write %s: %s", path, exc)

        try:
            provisioned_marker().touch()
        except OSError as exc:
            logger.error("Cannot create provisioning marker: %s", exc)


def _write_desktop(path: Path, entry: dict[str, str]) -> None:
    """Write one ``[Desktop Entry]`` mapping to *path* (mirror of _parse_desktop).

    Same ``configparser`` mechanics, case-sensitive keys, and the leading
    Kasual-Desktop comment as the bundled examples carry."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # .desktop keys are case-sensitive
    parser["Desktop Entry"] = entry
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Kasual Desktop app entry\n")
        parser.write(handle, space_around_delimiters=False)
