"""Wallpaper resolution for wlroots compositors (Sway, Hyprland, Wayfire).

Resolved fresh on every Kasual launch, so a wallpaper changed in the compositor
is picked up on the next restart. When no wallpaper daemon reports one and no
known convention file holds it, it falls back to the static ``<config>/wallpaper``
file.
"""

from __future__ import annotations

import configparser
import logging
import os
import re
import subprocess
from pathlib import Path

from domain.shell.wallpaper import SystemWallpaper, Wallpaper
from infrastructure.linux.display.wallpaper import StaticFileWallpaper, pcmanfm_image

logger = logging.getLogger(__name__)

_CLI_TIMEOUT_S = 2.0


_HYDE_CURRENT = "hypr/wallpaper_effects/.wallpaper_current"


class HyprlandWallpaper(SystemWallpaper):
    """Current Hyprland wallpaper, whichever daemon set it.

    swww and hyprpaper are both common, and setups like HyDE track the live
    wallpaper as a plain file, so each source is tried in turn before the static
    fallback.
    """

    def current(self) -> Wallpaper | None:
        for source in (self._swww_path, self._hyprpaper_path, self._hyde_path):
            path = source()
            if path:
                logger.info("Hyprland wallpaper: %s", path)
                return Wallpaper(image_path=path)
        return StaticFileWallpaper().current()

    def _swww_path(self) -> str | None:
        out = self._run(["swww", "query"])
        if out is None:
            return None
        for line in out.splitlines():
            _, sep, path = line.partition("image: ")
            path = path.strip()
            if sep and os.path.isfile(path):
                return path
        return None

    def _hyprpaper_path(self) -> str | None:
        out = self._run(["hyprctl", "hyprpaper", "listactive"])
        if out is None:
            return None
        for line in out.splitlines():
            _, sep, path = line.partition("=")
            path = path.strip()
            if sep and os.path.isfile(path):
                return path
        return None

    def _hyde_path(self) -> str | None:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        current = Path(base) / _HYDE_CURRENT
        return str(current) if current.is_file() else None

    def _run(self, argv: list[str]) -> str | None:
        try:
            return subprocess.run(
                argv, timeout=_CLI_TIMEOUT_S, check=True, capture_output=True, text=True,
            ).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("%s failed: %s", argv[0], exc)
            return None


# output <name> bg <path> <mode> — the mode keyword bounds a path that may hold spaces.
_SWAY_BG_RE = re.compile(
    r"\boutput\b.*?\bbg\s+(?P<path>.+?)\s+"
    r"(?:fill|stretch|fit|center|tile|solid_color)\b"
)


class SwayWallpaper(SystemWallpaper):
    """Current wallpaper parsed from the Sway config's ``output ... bg`` line."""

    def current(self) -> Wallpaper | None:
        path = self._config_bg()
        if path:
            logger.info("Sway wallpaper: %s", path)
            return Wallpaper(image_path=path)
        return StaticFileWallpaper().current()

    def _config_bg(self) -> str | None:
        for config in self._config_paths():
            path = self._scan(config)
            if path:
                return path
        return None

    def _config_paths(self) -> list[Path]:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        return [Path(base) / "sway" / "config", Path("/etc/sway/config")]

    def _scan(self, config: Path) -> str | None:
        try:
            text = config.read_text(encoding="utf-8")
        except OSError:
            return None
        found: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = _SWAY_BG_RE.search(stripped)
            if match:
                candidate = os.path.expanduser(match.group("path").strip("'\""))
                if os.path.isfile(candidate):
                    found = candidate   # a later line overrides an earlier one
        return found


_WF_SHELL_USER_CONFIG = "wf-shell.ini"
_WF_SHELL_SYSTEM_CONFIG = Path("/etc/wayfire/wf-shell-defaults.ini")
# wf-background's own default, from wf-shell's metadata: with no ini at all, this
# is the image on screen.
_WF_BACKGROUND_DEFAULT_IMAGE = "/usr/share/wayfire/wallpaper.jpg"
_IMAGE_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".jxl", ".tif", ".tiff",
})


class WayfireWallpaper(SystemWallpaper):
    """Current wallpaper of a Wayfire session.

    Two desktops draw one, and neither knows about the other: Raspberry Pi OS
    hands the desktop to pcmanfm, while a plain Wayfire session has wf-shell's
    wf-background, which takes ``background/image`` from wf-shell.ini. pcmanfm
    goes first — where it runs, wf-background's default image is still on disk
    and would otherwise win over the wallpaper the user actually set.
    """

    def current(self) -> Wallpaper | None:
        for source in (pcmanfm_image, self._wf_background_image):
            path = source()
            if path:
                logger.info("Wayfire wallpaper: %s", path)
                return Wallpaper(image_path=path)
        return StaticFileWallpaper().current()

    def _wf_background_image(self) -> str | None:
        configured = self._configured_image() or _WF_BACKGROUND_DEFAULT_IMAGE
        return _image_or_first_in_directory(configured)

    def _configured_image(self) -> str | None:
        for config in self._configs():
            parser = configparser.ConfigParser(interpolation=None)
            try:
                parser.read(config, encoding="utf-8")
            except (OSError, configparser.Error) as exc:
                logger.debug("Unreadable wf-shell config %s: %s", config, exc)
                continue
            image = parser.get("background", "image", fallback="").strip()
            if image:
                return os.path.expanduser(image)
        return None

    def _configs(self) -> list[Path]:
        base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
        return [Path(base) / _WF_SHELL_USER_CONFIG, _WF_SHELL_SYSTEM_CONFIG]


def _image_or_first_in_directory(path: str) -> str | None:
    """wf-background takes either an image or a directory it cycles through; of a
    directory Kasual Desktop shows the first image, since it cycles nothing."""
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        return next(
            (str(entry) for entry in sorted(Path(path).iterdir())
             if entry.is_file() and entry.suffix.lower() in _IMAGE_SUFFIXES),
            None,
        )
    return None
