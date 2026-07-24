"""Wallpaper resolution for COSMIC, read from cosmic-config on disk.

cosmic-bg publishes nothing queryable, so its configuration is read the way it
reads it: one file per key under ``com.system76.CosmicBackground/v1``, with the
user's config directory layered over the system defaults. Resolved fresh on every
launch, so a wallpaper changed in COSMIC Settings is picked up on restart.

An entry names its image as ``source: Path("…")``. That path may be a directory —
COSMIC's rotating slideshow — in which case the first image in the compositor's
own alphanumeric order stands in for it. A ``source: Color(…)`` entry has no image
at all, and falls through to the static file the other Wayland backends use.
"""

from __future__ import annotations

import logging
import os
import re

from pathlib import Path

from domain.shell.wallpaper import SystemWallpaper, Wallpaper
from infrastructure.linux.display.wallpaper import StaticFileWallpaper

logger = logging.getLogger(__name__)

_COMPONENT = "com.system76.CosmicBackground/v1"
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})

_SOURCE_RE = re.compile(r'source:\s*Path\("([^"]+)"\)')
_OUTPUT_RE = re.compile(r'Output\("([^"]+)"\)')


class CosmicSystemWallpaper(SystemWallpaper):
    def current(self) -> Wallpaper | None:
        path = self._configured_image()
        if path:
            logger.info("COSMIC wallpaper: %s", path)
            return Wallpaper(image_path=path)
        return StaticFileWallpaper().current()

    def _configured_image(self) -> str | None:
        for key in self._entry_keys():
            entry = self._read(key)
            if entry is None:
                continue
            match = _SOURCE_RE.search(entry)
            if match is None:
                continue
            image = self._resolve(match.group(1))
            if image:
                return image
        return None

    def _entry_keys(self) -> list[str]:
        """The entry keys to try, most specific first.

        With ``same-on-all`` set there is only the shared ``all`` entry; otherwise
        each output listed in ``backgrounds`` has its own, and ``all`` remains the
        fallback for outputs that never got one.
        """
        if (self._read("same-on-all") or "").strip() != "false":
            return ["all"]
        listed = self._read("backgrounds") or ""
        return [f"output.{name}" for name in _OUTPUT_RE.findall(listed)] + ["all"]

    def _read(self, key: str) -> str | None:
        for base in _config_dirs():
            try:
                return (base / _COMPONENT / key).read_text(encoding="utf-8")
            except OSError:
                continue
        return None

    def _resolve(self, source: str) -> str | None:
        path = os.path.expanduser(source)
        if os.path.isfile(path):
            return path
        if os.path.isdir(path):
            return _first_image(Path(path))
        logger.debug("COSMIC wallpaper source is not on disk: %s", path)
        return None


def _config_dirs() -> list[Path]:
    """Where cosmic-config looks: the user's own config, then the system defaults."""
    config_home = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(config_home) / "cosmic",
            *(Path(d) / "cosmic" for d in data_dirs.split(":") if d)]


def _first_image(directory: Path) -> str | None:
    try:
        images = sorted(entry for entry in directory.iterdir()
                        if entry.suffix.lower() in _IMAGE_SUFFIXES and entry.is_file())
    except OSError:
        return None
    return str(images[0]) if images else None
