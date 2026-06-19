"""Override qtawesome's Font Awesome 5 fonts with the bundled originals.

Distro ``python3-qtawesome`` (+dfsg) ships *Fork Awesome* (FA 4.7) under the FA5
prefixes while keeping qtawesome's FA5 charmap, so FA5-only glyphs render as
random fallback characters. We re-register the genuine FA5 webfonts bundled at
the install root (shared with the main app). Call after ``QApplication`` exists,
before any icon is created.
"""

import logging
from pathlib import Path

import qtawesome as qta

logger = logging.getLogger(__name__)

# Shared fonts dir at the install root: apps/file_browser/src -> .../fonts
_FONTS_DIR = Path(__file__).resolve().parents[3] / "fonts"

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
        qta.load_font(prefix, ttf, charmap, directory=str(_FONTS_DIR))
