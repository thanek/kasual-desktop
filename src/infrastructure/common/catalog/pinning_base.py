"""Shared base for the *Pin to menu* adapters across platforms.

Pinning turns a dynamic open-window tile into a configured app by writing a Kasual
app ``.desktop`` into the catalog directory. The *placement* mechanics — choosing
the next sort order, a unique filename, reading an entry back, and unpinning — are
identical on every platform and live here. Only how a window is resolved to a
launchable :class:`App` differs (Linux looks up the freedesktop ``.desktop``;
Windows derives it from the window's process), so each platform's adapter
subclasses this and implements :meth:`pin`.
"""

import configparser
import logging
import re
from pathlib import Path

from domain.catalog.app import App
from domain.catalog.window import Window
from domain.menu.ports import AppPinning

from .app_config import _ordered_desktop_paths, _write_desktop, apps_dir  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)


class AppPinningBase(AppPinning):
    """Platform-neutral placement/unpin mechanics; subclasses implement ``pin``."""

    def pin(self, window: Window) -> App | None:  # pragma: no cover - abstract
        raise NotImplementedError

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

    def _persist(self, window: Window, app: App) -> App | None:
        """Write *app* as a pinned tile in the catalog directory; return *app*
        on success, None on I/O failure.

        The shared tail of a platform pin: ensure the catalog dir, allocate the
        next sort order and a unique filename, write the ``.desktop`` entry and
        log. Subclasses build the resolved :class:`App` from the window and call
        this to do the on-disk work, so the placement mechanics stay in one
        place (mirroring :meth:`App.to_desktop_entry`'s shape).
        """
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
