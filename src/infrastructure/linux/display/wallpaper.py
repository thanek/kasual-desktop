"""SystemWallpaper for sessions with no wallpaper daemon to query.

Off Plasma the background is whatever ``<config>/wallpaper`` resolves to — a
copied image or a symlink into the user's own collection. When it is absent the
Desktop renders its own background.

The pcmanfm family is the exception: Raspberry Pi OS draws its labwc and wayfire
desktops with pcmanfm, LXQt draws its own with pcmanfm-qt, and both name the
image in a profile config, so Kasual Desktop can inherit the wallpaper the user
already set.
"""

import configparser
import logging
import os
from pathlib import Path

from domain.shell.wallpaper import SystemWallpaper, Wallpaper
from infrastructure.common.catalog.app_config import config_root

logger = logging.getLogger(__name__)

_PCMANFM_CONFIGS = (
    "pcmanfm/*/desktop-items-*.conf",   # pcmanfm, one config per monitor
    "pcmanfm-qt/*/settings.conf",       # pcmanfm-qt, everything in one
)
_MODE_KEYS = ("wallpaper_mode", "wallpapermode")   # pcmanfm's, then pcmanfm-qt's


class StaticFileWallpaper(SystemWallpaper):
    def current(self) -> Wallpaper | None:
        path = config_root() / "wallpaper"
        if not path.is_file():
            logger.debug("No wallpaper configured at %s", path)
            return None
        logger.info("Static wallpaper: %s", path)
        return Wallpaper(image_path=str(path))


def pcmanfm_image() -> str | None:
    """The image the pcmanfm desktop draws, or None where it draws none.

    Profiles are globbed rather than named: Raspberry Pi OS ships ``LXDE-pi`` and
    a per-compositor variant of it, LXQt ships ``lxqt``, and pcmanfm gives each
    monitor its own ``desktop-items-<n>.conf`` — the first config that names a
    readable image wins.
    """
    for config in _pcmanfm_configs():
        path = _image_in(config)
        if path:
            return path
    return None


def _pcmanfm_configs() -> list[Path]:
    user_config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    system_config = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    directories = [user_config, *system_config.split(":")]
    return [config
            for directory in directories if directory
            for pattern in _PCMANFM_CONFIGS
            for config in sorted(Path(directory).glob(pattern))]


def _image_in(config: Path) -> str | None:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        logger.debug("Unreadable pcmanfm config %s: %s", config, exc)
        return None
    for section in parser.sections():
        if any(parser.get(section, key, fallback="") == "color" for key in _MODE_KEYS):
            continue
        path = os.path.expanduser(parser.get(section, "wallpaper", fallback=""))
        if path and os.path.isfile(path):
            return path
    return None


class PcmanfmWallpaper(SystemWallpaper):
    """The pcmanfm desktop's wallpaper, else the static file."""

    def current(self) -> Wallpaper | None:
        path = pcmanfm_image()
        if path:
            logger.info("pcmanfm wallpaper: %s", path)
            return Wallpaper(image_path=path)
        return StaticFileWallpaper().current()
