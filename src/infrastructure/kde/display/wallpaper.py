"""Resolving KDE Plasma's current wallpaper from its appletsrc config.

The SystemWallpaper port backed by `plasma-org.kde.plasma.desktop-appletsrc`:
reads the configured image, expanding a wallpaper *package* (a directory with
contents/images/WxH.ext) to its highest-resolution image. Pure config/file I/O,
no Qt — it hands back a domain `Wallpaper` (a path); rendering is the view's job.
"""

import configparser
import logging
import os
from pathlib import Path

from domain.shell.wallpaper import SystemWallpaper, Wallpaper

logger = logging.getLogger(__name__)

_CFG_PATH = Path.home() / '.config' / 'plasma-org.kde.plasma.desktop-appletsrc'


class KdeSystemWallpaper(SystemWallpaper):
    """Reads the KDE Plasma wallpaper setting and returns it as a `Wallpaper`.

    Handles both direct file paths and wallpaper packages
    (directory with contents/images/WxH.ext).
    """

    def current(self) -> Wallpaper | None:
        if not _CFG_PATH.exists():
            logger.warning('Could not find plasma config file: %s', _CFG_PATH)
            return None

        cp = configparser.RawConfigParser()
        cp.read(str(_CFG_PATH), encoding='utf-8')

        for section in cp.sections():
            if '][Wallpaper][' not in section:
                continue
            raw = cp.get(section, 'Image', fallback=None)
            if not raw:
                continue

            raw = raw.strip("'\"")
            path = raw[7:] if raw.startswith('file://') else raw

            if os.path.isdir(path):
                resolved = self._best_package_image(path)
                if resolved:
                    path = resolved
                else:
                    logger.debug('No images in path: %s', path)
                    continue

            if not os.path.isfile(path):
                logger.debug('Ommitting (not a file): %s', path)
                continue

            logger.info('KDE wallpaper: %s', path)
            return Wallpaper(image_path=path)

        logger.warning('No wallpaper found in Plasma configuration')
        return None

    def _best_package_image(self, directory: str) -> str | None:
        """Returns the highest-resolution image from a wallpaper package, or None."""
        images_dir = os.path.join(directory, 'contents', 'images')
        if not os.path.isdir(images_dir):
            return None

        best: tuple[int, str] = (0, '')
        for fname in os.listdir(images_dir):
            fpath = os.path.join(images_dir, fname)
            if not os.path.isfile(fpath):
                continue
            name = os.path.splitext(fname)[0]
            if 'x' in name:
                try:
                    w, h = name.split('x', 1)
                    pixels = int(w) * int(h)
                    if pixels > best[0]:
                        best = (pixels, fpath)
                except ValueError:
                    pass
            elif best[0] == 0:
                best = (1, fpath)

        return best[1] or None
