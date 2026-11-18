"""The bundled Font Awesome 5 fonts in place of the distro's qtawesome ones."""

import logging
from pathlib import Path

import qtawesome as qta
from qtawesome.iconic_font import IconicFont

logger = logging.getLogger(__name__)

_INSTALL_ROOT = Path(__file__).resolve().parents[3]
_FONTS_DIR = _INSTALL_ROOT / "fonts"

_FA5_FONTS = {
    "fa5": ("fontawesome5-regular-webfont-5.15.4.ttf", "fontawesome5-regular-webfont-charmap-5.15.4.json"),
    "fa5s": ("fontawesome5-solid-webfont-5.15.4.ttf", "fontawesome5-solid-webfont-charmap-5.15.4.json"),
    "fa5b": ("fontawesome5-brands-webfont-5.15.4.ttf", "fontawesome5-brands-webfont-charmap-5.15.4.json"),
    "fa5r": ("fontawesome5-regular-webfont-5.15.4.ttf", "fontawesome5-regular-webfont-charmap-5.15.4.json"),
}

_QTAWESOME_FONTS_DIR = Path(qta.__file__).resolve().parent / "fonts"


def install_bundled_fontawesome5() -> None:
    qta._resource["iconic"] = IconicFont(*_bundled_fa5_fonts(), *_readable_qtawesome_fonts())
    logger.info("Loaded bundled Font Awesome 5 fonts from %s", _FONTS_DIR)


def _bundled_fa5_fonts() -> list[tuple[str, str, str, str]]:
    return [
        (prefix, ttf, charmap, str(_FONTS_DIR))
        for prefix, (ttf, charmap) in _FA5_FONTS.items()
        if (_FONTS_DIR / ttf).is_file()
    ]


def _readable_qtawesome_fonts() -> list[tuple[str, str, str, str]]:
    fonts = []
    for prefix, ttf, charmap in qta._BUNDLED_FONTS:
        if prefix in _FA5_FONTS:
            continue
        if not (_QTAWESOME_FONTS_DIR / ttf).is_file():
            logger.warning("qtawesome font unreadable, prefix %s disabled: %s", prefix, ttf)
            continue
        fonts.append((prefix, ttf, charmap, str(_QTAWESOME_FONTS_DIR)))
    return fonts
