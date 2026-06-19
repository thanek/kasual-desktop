"""Override qtawesome's Font Awesome 5 fonts with the bundled originals.

Debian/Ubuntu repackage ``python3-qtawesome`` under ``+dfsg`` and swap the real
Font Awesome 5 webfonts for *Fork Awesome* (a Font Awesome 4.7 fork) while
keeping qtawesome's FA5 *charmap*. The codepoints then point at glyphs the Fork
Awesome font does not have (FA5-only icons like ``network-wired``), so Qt falls
back to an unrelated system font — the icons render as random CJK/Arabic glyphs.

We ship the genuine FA5 5.15.4 webfonts (SIL OFL 1.1) and re-register them under
the ``fa5s``/``fa5b``/``fa5r`` prefixes, overriding whatever qtawesome loaded.
Must be called after a ``QApplication`` exists and before any icon is created.
"""

import logging
from pathlib import Path

import qtawesome

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).resolve().parents[3] / "fonts"

# prefix -> (ttf filename, charmap filename) for the genuine FA5 webfonts.
_FA5_FONTS = {
    "fa5s": ("fontawesome5-solid-webfont-5.15.4.ttf", "fontawesome5-solid-webfont-charmap-5.15.4.json"),
    "fa5b": ("fontawesome5-brands-webfont-5.15.4.ttf", "fontawesome5-brands-webfont-charmap-5.15.4.json"),
    "fa5r": ("fontawesome5-regular-webfont-5.15.4.ttf", "fontawesome5-regular-webfont-charmap-5.15.4.json"),
}


def install_fontawesome5() -> None:
    """Re-register the bundled FA5 fonts so glyphs match qtawesome's charmap."""
    for prefix, (ttf, charmap) in _FA5_FONTS.items():
        if not (_FONTS_DIR / ttf).is_file():
            logger.warning("Bundled font missing: %s — keeping qtawesome default", ttf)
            continue
        qtawesome.load_font(prefix, ttf, charmap, directory=str(_FONTS_DIR))
    logger.info("Loaded bundled Font Awesome 5 fonts from %s", _FONTS_DIR)
