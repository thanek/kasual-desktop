"""Single application tile displayed on the desktop tile bar."""

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QToolButton, QLabel, QGraphicsDropShadowEffect

from ui import styles

TILE_W = 180
TILE_H = 200


class AppTile(QWidget):
    """Single application tile."""

    clicked = pyqtSignal()

    def __init__(self, name: str, icon_name: str, color: str, qicon=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(TILE_W, TILE_H)
        self._color = color

        self._btn = QToolButton(self)
        self._btn.setFixedSize(TILE_W, TILE_H)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._btn.setIconSize(QSize(72, 72))
        if qicon is not None and not qicon.isNull():
            self._btn.setIcon(qicon)
        else:
            try:
                self._btn.setIcon(qta.icon(icon_name, color="white"))
            except Exception:
                self._btn.setIcon(qta.icon("fa5s.desktop", color="white"))
        self._btn.setText(name)
        self._btn.setStyleSheet(styles.tile_normal(color))
        self._btn.clicked.connect(self.clicked)

        self._dot = QLabel(self)
        self._dot.setFixedSize(14, 14)
        self._dot.setStyleSheet(
            "background-color: #a3be8c; border-radius: 7px; border: 2px solid #0b140e;"
        )
        self._dot.move(TILE_W - 22, 8)
        self._dot.hide()

        shadow = QGraphicsDropShadowEffect(self._btn)
        shadow.setOffset(4, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setBlurRadius(18)
        self._btn.setGraphicsEffect(shadow)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self._btn.setStyleSheet(styles.tile_selected())
            effect = QGraphicsDropShadowEffect(self._btn)
            effect.setOffset(0, 0)
            effect.setColor(QColor("#88c0d0"))
            effect.setBlurRadius(36)
            self._btn.setGraphicsEffect(effect)
        else:
            self._btn.setStyleSheet(styles.tile_normal(self._color))
            shadow = QGraphicsDropShadowEffect(self._btn)
            shadow.setOffset(4, 6)
            shadow.setColor(QColor(0, 0, 0, 160))
            shadow.setBlurRadius(18)
            self._btn.setGraphicsEffect(shadow)

    def set_running(self, running: bool) -> None:
        self._dot.setVisible(running)
