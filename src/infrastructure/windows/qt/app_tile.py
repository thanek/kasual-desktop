"""Single application tile displayed on the Windows tile bar."""

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, QPoint, QEasingCurve, QPropertyAnimation, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QFontMetrics
from PyQt6.QtWidgets import QWidget, QToolButton, QLabel

TILE_W        = 180
TILE_H        = 200
TILE_SEL_W    = round(TILE_W * 1.20)
TILE_SEL_H    = round(TILE_H * 1.20)
ICON_SIZE     = 84
ICON_SIZE_SEL = round(ICON_SIZE * 1.20)
BAR_W_RATIO   = 0.7
BAR_H         = 8
BAR_MARGIN    = 12
SCALE_ANIM_MS = 160
BTN_OFFSET_X  = (TILE_SEL_W - TILE_W) // 2
BTN_OFFSET_Y  = (TILE_SEL_H - TILE_H) // 2


def _tile_normal(color: str) -> str:
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: none;
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


def _tile_selected(color: str) -> str:
    return f"""
        QToolButton {{
            font-size: 18px;
            font-weight: bold;
            color: white;
            background-color: {color};
            border: 3px solid white;
            border-radius: 32px;
            padding: 12px 8px 16px 8px;
        }}
    """


class WindowsAppTile(QWidget):
    """Single application tile for Windows."""

    clicked       = pyqtSignal()
    hovered       = pyqtSignal()
    right_clicked = pyqtSignal()

    def __init__(self, name: str, icon_name: str, color: str, qicon=None, full_name: str | None = None, parent=None):
        super().__init__(parent)
        self._color = color
        self._full_name = full_name if full_name is not None else name
        self._is_selected = False
        self._closing = False
        self._pos_at_leave: QPoint | None = None
        self._scale_t = 0.0
        self._scale_anim: QVariantAnimation | None = None
        self._running = False

        self._btn = QToolButton(self)
        self._btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        if qicon is not None and not qicon.isNull():
            self._btn.setIcon(qicon)
        else:
            try:
                self._btn.setIcon(qta.icon(icon_name, color="white"))
            except Exception:
                self._btn.setIcon(qta.icon("fa5s.desktop", color="white"))
        self._btn.setText(name)
        self._btn.setStyleSheet(_tile_normal(color))
        self._btn.clicked.connect(self.clicked)

        self._status_bar = QLabel(self)
        self._status_bar.hide()

        self.setFixedSize(TILE_SEL_W, TILE_SEL_H)
        self._refit(TILE_W, TILE_H, ICON_SIZE)

    def click(self) -> None:
        self._btn.click()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        pos = event.globalPosition().toPoint()
        synthetic = pos == self._pos_at_leave
        self._pos_at_leave = None
        if not synthetic:
            self.hovered.emit()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._pos_at_leave = QCursor.pos()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        else:
            super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        if selected == self._is_selected:
            return
        self._is_selected = selected
        if selected:
            self._btn.setStyleSheet(_tile_selected(self._color))
            self._animate_scale(to_selected=True)
        else:
            self._btn.setStyleSheet(_tile_normal(self._color))
            self._animate_scale(to_selected=False)

    def set_moving(self, moving: bool) -> None:
        style = f"""
            QToolButton {{
                font-size: 18px;
                font-weight: bold;
                color: white;
                background-color: {self._color};
                border: 3px dashed white;
                border-radius: 32px;
                padding: 12px 8px 16px 8px;
            }}
        """ if moving else _tile_selected(self._color)
        self._btn.setStyleSheet(style)

    def set_color(self, color: str) -> None:
        self._color = color
        style = _tile_selected if self._is_selected else _tile_normal
        self._btn.setStyleSheet(style(color))

    def set_running(self, running: bool) -> None:
        self._running = running
        if not running:
            self._closing = False
            self._status_bar.hide()
        elif not self._closing:
            self._show_status_bar("#a3be8c")

    def set_closing(self) -> None:
        self._closing = True
        self._show_status_bar("#d08770")

    def is_closing(self) -> bool:
        return self._closing

    def _refit(self, w: int, h: int, icon: int) -> None:
        ox = (TILE_SEL_W - w) // 2
        oy = (TILE_SEL_H - h) // 2
        self._btn.move(ox, oy)
        self._btn.setFixedSize(w, h)
        self._btn.setIconSize(QSize(icon, icon))
        bar_w = round(w * BAR_W_RATIO)
        self._status_bar.setFixedSize(bar_w, BAR_H)
        self._status_bar.move(ox + (w - bar_w) // 2, oy + h - BAR_H - BAR_MARGIN)

    def _animate_scale(self, to_selected: bool) -> None:
        target = 1.0 if to_selected else 0.0
        if self._scale_anim is not None:
            self._scale_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._scale_t)
        anim.setEndValue(target)
        anim.setDuration(SCALE_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._apply_scale)
        anim.start()
        self._scale_anim = anim

    def _apply_scale(self, t) -> None:
        self._scale_t = float(t)
        w    = round(TILE_W    + (TILE_SEL_W    - TILE_W)    * self._scale_t)
        h    = round(TILE_H    + (TILE_SEL_H    - TILE_H)    * self._scale_t)
        icon = round(ICON_SIZE + (ICON_SIZE_SEL - ICON_SIZE) * self._scale_t)
        self._refit(w, h, icon)

    def _show_status_bar(self, color: str) -> None:
        self._status_bar.setStyleSheet(
            f"background-color: {color}; border-radius: {BAR_H // 2}px; border: 1px solid #0b140e;"
        )
        self._status_bar.show()