"""Loading KDE Plasma wallpaper from plasma-org.kde.plasma.desktop-appletsrc."""

import configparser
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _wallpaper_package_image(directory: str) -> str | None:
    """
    Looks for the best image in a KDE wallpaper package (contents/images/ directory).
    Returns the path to the file with the highest resolution, or None.
    """
    images_dir = os.path.join(directory, 'contents', 'images')
    if not os.path.isdir(images_dir):
        return None

    best: tuple[int, str] = (0, '')
    for fname in os.listdir(images_dir):
        fpath = os.path.join(images_dir, fname)
        if not os.path.isfile(fpath):
            continue
        # File names have the format WxH.ext — parse resolution
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
            best = (1, fpath)   # fallback: any file

    return best[1] or None


def load_kde_wallpaper() -> 'QPixmap | None':
    """
    Reads the wallpaper path from plasma-org.kde.plasma.desktop-appletsrc
    and returns a QPixmap, or None if the file could not be found.

    Handles both direct file paths and KDE wallpaper packages
    (directory with contents/images/WxH.ext).
    """
    from PyQt6.QtGui import QPixmap

    cfg_path = Path.home() / '.config' / 'plasma-org.kde.plasma.desktop-appletsrc'
    if not cfg_path.exists():
        logger.warning('Could not find plasma config file: %s', cfg_path)
        return None

    cp = configparser.RawConfigParser()
    cp.read(str(cfg_path), encoding='utf-8')

    for section in cp.sections():
        if '][Wallpaper][' not in section:
            continue
        raw = cp.get(section, 'Image', fallback=None)
        if not raw:
            continue

        # Strip optional quotes and file:// prefix
        raw = raw.strip("'\"")
        path = raw[7:] if raw.startswith('file://') else raw

        # Wallpaper package (directory) → find the best image in contents/images/
        if os.path.isdir(path):
            resolved = _wallpaper_package_image(path)
            if resolved:
                path = resolved
            else:
                logger.debug('No images in path: %s', path)
                continue

        if not os.path.isfile(path):
            logger.debug('Ommitting (not a file): %s', path)
            continue

        px = QPixmap(path)
        if px.isNull():
            logger.debug('Could not read: %s', path)
            continue

        logger.info('KDE wallpaper: %s', path)
        return px

    logger.warning('No wallpaper found in Plasma configuration')
    return None
