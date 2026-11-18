"""Qt icons for apps and windows, drawn with the bundled Font Awesome 5 fonts."""

import logging
from pathlib import Path

import qtawesome
from qtawesome.iconic_font import IconicFont
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon

from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_icon_provider = None


def fitted_icon(icon: QIcon | None, size: int) -> QIcon | None:
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
    if not path:
        return None
    import os
    from PyQt6.QtCore import QFileInfo
    info = QFileInfo(path)
    if not info.exists():
        return None
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

_FA5_FONTS = {
    "fa5": ("fontawesome5-regular-webfont-5.15.4.ttf", "fontawesome5-regular-webfont-charmap-5.15.4.json"),
    "fa5s": ("fontawesome5-solid-webfont-5.15.4.ttf", "fontawesome5-solid-webfont-charmap-5.15.4.json"),
    "fa5b": ("fontawesome5-brands-webfont-5.15.4.ttf", "fontawesome5-brands-webfont-charmap-5.15.4.json"),
    "fa5r": ("fontawesome5-regular-webfont-5.15.4.ttf", "fontawesome5-regular-webfont-charmap-5.15.4.json"),
}

_QTAWESOME_FONTS_DIR = Path(qtawesome.__file__).resolve().parent / "fonts"


def install_bundled_fontawesome5() -> None:
    qtawesome._resource["iconic"] = IconicFont(*_bundled_fa5_fonts(), *_readable_qtawesome_fonts())
    logger.info("Loaded bundled Font Awesome 5 fonts from %s", _FONTS_DIR)


def _bundled_fa5_fonts() -> list[tuple[str, str, str, str]]:
    return [
        (prefix, ttf, charmap, str(_FONTS_DIR))
        for prefix, (ttf, charmap) in _FA5_FONTS.items()
        if (_FONTS_DIR / ttf).is_file()
    ]


def _readable_qtawesome_fonts() -> list[tuple[str, str, str, str]]:
    fonts = []
    for prefix, ttf, charmap in qtawesome._BUNDLED_FONTS:
        if prefix in _FA5_FONTS:
            continue
        if not (_QTAWESOME_FONTS_DIR / ttf).is_file():
            logger.warning("qtawesome font unreadable, prefix %s disabled: %s", prefix, ttf)
            continue
        fonts.append((prefix, ttf, charmap, str(_QTAWESOME_FONTS_DIR)))
    return fonts
