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
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon

from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_icon_provider = None


def fitted_icon(icon: QIcon | None, size: int) -> QIcon | None:
    """*icon* enlarged to *size* when it only ships smaller pixmaps.

    QIcon never upscales: an app whose only themed icon is 32px (Steam's per-game
    icons, for one) hands back a 32px pixmap however large the request, and the
    widget centres that stamp inside the tile."""
    if icon is None or icon.isNull():
        return icon
    pixmap = icon.pixmap(QSize(size, size))
    if pixmap.isNull():
        return icon
    ratio = pixmap.devicePixelRatio()
    if max(pixmap.width(), pixmap.height()) / ratio >= size:
        return icon
    target = QSize(round(size * ratio), round(size * ratio))
    scaled = pixmap.scaled(
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(ratio)
    return QIcon(scaled)


def resolve_app_icon(app) -> QIcon | None:
    if app.icon_theme:
        themed = QIcon.fromTheme(app.icon_theme)
        if not themed.isNull():
            return themed
    if app.icon:
        try:
            return qtawesome.icon(app.icon, color="white")
        except Exception as exc:
            logger.debug("qtawesome icon %r unavailable: %s", app.icon, exc)
    return shell_icon(app.command)


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
        from infrastructure.windows.qt.win_icons import jumbo_icon
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
