"""Load Kasual app definitions from freedesktop ``.desktop`` files.

Apps live in ``$XDG_CONFIG_HOME/kasual-desktop/apps/*.desktop`` (defaulting to
``~/.config/...``). Standard ``[Desktop Entry]`` keys plus ``X-Kasual-*``
extensions map to the app dicts consumed by the Desktop / TileBar / AppManager.

This module is intentionally Qt-free: ``load_apps()`` runs before the
``QApplication`` exists (see ``main.py``), so themed-icon resolution is deferred
to the TileBar, which runs in the Qt context. We only carry the raw ``Icon``
name through as ``icon_theme``.
"""

import configparser
import logging
import os
import shlex
from pathlib import Path

from domain.app import App

logger = logging.getLogger(__name__)

# freedesktop Exec field codes — meaningless for our launcher (we pass no files
# or URLs), so they are stripped. See the Desktop Entry Specification.
_FIELD_CODES = {
    "%f", "%F", "%u", "%U", "%i", "%c", "%k",
    "%d", "%D", "%n", "%N", "%v", "%m",
}

# Apps without X-Kasual-Order sort after explicitly-ordered ones (ties: filename).
_ORDER_DEFAULT = 10_000


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


def _parse_desktop(path: Path) -> tuple[int, App] | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # .desktop keys are case-sensitive
    parser.read(path, encoding="utf-8")

    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]

    if entry.get("Type", "Application") != "Application":
        return None
    if entry.get("NoDisplay", "false").strip().lower() == "true":
        return None
    if entry.get("Hidden", "false").strip().lower() == "true":
        return None

    name = (entry.get("Name") or "").strip()
    exec_str = (entry.get("Exec") or "").strip()
    if not name or not exec_str:
        logger.warning("Skipping %s: missing Name or Exec", path.name)
        return None

    command, args = _parse_exec(exec_str)
    if command is None:
        logger.warning("Skipping %s: empty Exec after parsing", path.name)
        return None

    app = App(
        name=name,
        command=command,
        args=tuple(args),
        icon=(entry.get("X-Kasual-Icon") or "").strip() or None,
        icon_theme=(entry.get("Icon") or "").strip() or None,
        color=(entry.get("X-Kasual-Color") or "").strip() or "#2e3440",
        recall_menu_trigger=(entry.get("X-Kasual-RecallMenuTrigger") or "").strip()
                            or "BTN_MODE_CLICK",
        launch_hide_grace_ms=_parse_int(entry.get("X-Kasual-HideGraceMs"), 0),
        env=_parse_env(entry.get("X-Kasual-Env")),
    )
    order = _parse_int(entry.get("X-Kasual-Order"), _ORDER_DEFAULT)
    return order, app


def _parse_exec(exec_str: str) -> tuple[str | None, list[str]]:
    """Split a desktop ``Exec`` value into (command, args), dropping field codes."""
    cleaned: list[str] = []
    for token in shlex.split(exec_str):
        if token in _FIELD_CODES:
            continue
        cleaned.append(token.replace("%%", "%"))
    if not cleaned:
        return None, []
    return cleaned[0], cleaned[1:]


def _parse_env(raw: str | None) -> dict:
    """Parse ``X-Kasual-Env`` (``KEY1=val1;KEY2=val2``) into a dict."""
    env: dict[str, str] = {}
    if not raw:
        return env
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key:
            env[key] = value
    return env


def _parse_int(raw: str | None, default: int) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default
