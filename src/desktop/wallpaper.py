"""Ładowanie tapety KDE Plasma z plasma-org.kde.plasma.desktop-appletsrc."""

import configparser
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _wallpaper_package_image(directory: str) -> str | None:
    """
    Szuka najlepszego obrazu w paczce tapety KDE (katalog contents/images/).
    Zwraca ścieżkę do pliku o największej rozdzielczości lub None.
    """
    images_dir = os.path.join(directory, 'contents', 'images')
    if not os.path.isdir(images_dir):
        return None

    best: tuple[int, str] = (0, '')
    for fname in os.listdir(images_dir):
        fpath = os.path.join(images_dir, fname)
        if not os.path.isfile(fpath):
            continue
        # Nazwy plików mają format WxH.ext — parsuj rozdzielczość
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
            best = (1, fpath)   # fallback: jakikolwiek plik

    return best[1] or None


def load_kde_wallpaper() -> 'QPixmap | None':
    """
    Czyta ścieżkę tapety z plasma-org.kde.plasma.desktop-appletsrc
    i zwraca QPixmap lub None gdy nie udało się znaleźć pliku.

    Obsługuje zarówno bezpośrednie ścieżki do pliku jak i paczki tapety
    KDE (katalog z contents/images/WxH.ext).
    """
    from PyQt6.QtGui import QPixmap

    cfg_path = Path.home() / '.config' / 'plasma-org.kde.plasma.desktop-appletsrc'
    if not cfg_path.exists():
        logger.warning('Nie znaleziono pliku konfiguracji Plasma: %s', cfg_path)
        return None

    cp = configparser.RawConfigParser()
    cp.read(str(cfg_path), encoding='utf-8')

    for section in cp.sections():
        if '][Wallpaper][' not in section:
            continue
        raw = cp.get(section, 'Image', fallback=None)
        if not raw:
            continue

        # Usuń opcjonalne cudzysłowy i prefiks file://
        raw = raw.strip("'\"")
        path = raw[7:] if raw.startswith('file://') else raw

        # Paczka tapety (katalog) → znajdź najlepszy obraz w contents/images/
        if os.path.isdir(path):
            resolved = _wallpaper_package_image(path)
            if resolved:
                path = resolved
            else:
                logger.debug('Brak obrazów w paczce: %s', path)
                continue

        if not os.path.isfile(path):
            logger.debug('Pomijam (nie plik): %s', path)
            continue

        px = QPixmap(path)
        if px.isNull():
            logger.debug('Nie udało się wczytać: %s', path)
            continue

        logger.info('Tapeta KDE: %s', path)
        return px

    logger.warning('Nie znaleziono żadnej tapety w konfiguracji Plasma')
    return None
