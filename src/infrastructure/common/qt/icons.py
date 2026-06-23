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

import qtawesome
from PyQt6.QtGui import QIcon

from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_icon_provider = None


def shell_icon(path: str) -> QIcon | None:
    """The operating system's icon for *path* (a Windows ``.lnk`` resolves to its
    target's icon; an exe gives its own), or None when *path* is not an existing
    file. On Linux a shell-command 'path' (e.g. ``steam``) is not a file, so this
    is a no-op there."""
    if not path:
        return None
    import os
    from PyQt6.QtCore import QFileInfo
    info = QFileInfo(path)
    if not info.exists():
        return None
    # On Windows pull the real 256px "jumbo" icon — QFileIconProvider only ever
    # delivers the 32px shell icon (it won't upscale), so tiles looked tiny.
    if os.name == "nt":
        from infrastructure.windows.win_icons import jumbo_icon
        jumbo = jumbo_icon(path)
        if jumbo is not None and not jumbo.isNull():
            return jumbo
    from PyQt6.QtWidgets import QFileIconProvider
    global _icon_provider
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    icon = _icon_provider.icon(info)
    return icon if not icon.isNull() else None

_FONTS_DIR = bundled_dir("fonts")

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
