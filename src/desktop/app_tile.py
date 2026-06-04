"""Single application tile displayed on the desktop tile bar."""

import qtawesome as qta
from PyQt6.QtCore import (Qt, QSize, QPoint,
                          QPropertyAnimation, QSequentialAnimationGroup, QPauseAnimation,
                          pyqtSignal)
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QWidget, QToolButton, QLabel

from ui import styles

TILE_W        = 180
TILE_H        = 200
TILE_SEL_W    = round(TILE_W * 1.20)    # 216
TILE_SEL_H    = round(TILE_H * 1.20)    # 240
ICON_SIZE     = 84
ICON_SIZE_SEL = round(ICON_SIZE * 1.20) # 101
BAR_W_RATIO   = 0.7
BAR_H         = 8
BAR_MARGIN    = 12

MARQUEE_MS_PER_PX = 30    # scroll speed
MARQUEE_PAUSE_MS  = 900   # hold at each end before reversing

# Centering offset of the normal button within the always-fixed TILE_SEL_* slot.
# When selected the button fills the slot (offset 0,0); when not selected it sits
# centred with these margins, so activating a tile doesn't shift its neighbours.
BTN_OFFSET_X = (TILE_SEL_W - TILE_W) // 2   # 18
BTN_OFFSET_Y = (TILE_SEL_H - TILE_H) // 2   # 20


class AppTile(QWidget):
    """Single application tile."""

    clicked       = pyqtSignal()
    hovered       = pyqtSignal()
    right_clicked = pyqtSignal()

    def __init__(self, name: str, icon_name: str, color: str, qicon=None, full_name: str | None = None, parent=None):
        super().__init__(parent)
        self._color = color

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
        self._btn.setStyleSheet(styles.tile_normal(color))
        self._btn.clicked.connect(self.clicked)

        self._full_name   = full_name if full_name is not None else name
        self._is_selected = False
        self._marquee_seq: QSequentialAnimationGroup | None = None
        self._marquee_clip = QWidget(self)
        self._marquee_clip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._marquee_clip.hide()
        self._marquee_lbl = QLabel(self._marquee_clip)
        self._marquee_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._closing = False
        self._status_bar = QLabel(self)
        self._status_bar.hide()

        self.setFixedSize(TILE_SEL_W, TILE_SEL_H)
        self._refit(TILE_W, TILE_H, ICON_SIZE)
        self._apply_shadow(selected=False)

    # ── Public API ──────────────────────────────────────────────────────────

    def click(self) -> None:
        self._btn.click()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.hovered.emit()

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
            self._refit(TILE_SEL_W, TILE_SEL_H, ICON_SIZE_SEL)
            self._btn.setStyleSheet(styles.tile_selected())
            self._apply_shadow(selected=True)
            self._start_marquee()
        else:
            if self._marquee_seq is not None:
                self._marquee_seq.stop()
                self._marquee_seq = None
            self._marquee_clip.hide()
            self._refit(TILE_W, TILE_H, ICON_SIZE)
            self._btn.setStyleSheet(styles.tile_normal(self._color))
            self._apply_shadow(selected=False)

    def set_running(self, running: bool) -> None:
        if not running:
            self._closing = False
            self._status_bar.setGraphicsEffect(None)
            self._status_bar.hide()
        elif not self._closing:
            self._show_status_bar("#a3be8c")
        # running + closing: keep orange bar unchanged until process exits

    def set_closing(self) -> None:
        self._closing = True
        self._show_status_bar("#d08770")

    def is_closing(self) -> bool:
        return self._closing

    # ── Private helpers ─────────────────────────────────────────────────────

    def _apply_shadow(self, selected: bool) -> None:
        if selected:
            styles.apply_card_shadow(self, offset_x=0, offset_y=0, blur=90, alpha=180, color=styles.COLOR_ACCENT)
        else:
            styles.apply_card_shadow(self, offset_x=4, offset_y=6, blur=32, alpha=180)

    def _refit(self, w: int, h: int, icon: int) -> None:
        """Position and resize the button within the fixed TILE_SEL_W × TILE_SEL_H slot."""
        ox = (TILE_SEL_W - w) // 2
        oy = (TILE_SEL_H - h) // 2
        self._btn.move(ox, oy)
        self._btn.setFixedSize(w, h)
        self._btn.setIconSize(QSize(icon, icon))
        bar_w = round(w * BAR_W_RATIO)
        self._status_bar.setFixedSize(bar_w, BAR_H)
        self._status_bar.move(ox + (w - bar_w) // 2, oy + h - BAR_H - BAR_MARGIN)

    def _show_status_bar(self, color: str) -> None:
        self._status_bar.setStyleSheet(
            f"background-color: {color}; border-radius: {BAR_H // 2}px; border: 1px solid #0b140e;"
        )
        styles.apply_card_shadow(self._status_bar, offset_x=0, offset_y=0, blur=12, alpha=140, color=color)
        self._status_bar.show()

    def _start_marquee(self) -> None:
        clip_x = 4
        clip_y = 12 + ICON_SIZE_SEL + 4
        clip_w = TILE_SEL_W - 8
        clip_h = TILE_SEL_H - 16 - BAR_H - BAR_MARGIN - 4 - clip_y
        self._marquee_clip.setGeometry(clip_x, clip_y, clip_w, clip_h)
        self._marquee_clip.setStyleSheet(f"background-color: {styles.COLOR_ACCENT};")

        font = QFont()
        font.setPixelSize(18)
        font.setBold(True)
        self._marquee_lbl.setFont(font)
        self._marquee_lbl.setStyleSheet("color: black; background: transparent;")
        self._marquee_lbl.setText(self._full_name)

        text_w    = QFontMetrics(font).horizontalAdvance(self._full_name) + 16
        max_scroll = text_w - clip_w
        self._marquee_lbl.setFixedSize(max(text_w, clip_w), clip_h)
        if max_scroll <= 0:
            return

        self._marquee_lbl.move(0, 0)
        self._marquee_clip.show()
        if self._marquee_seq is not None:
            self._marquee_seq.stop()

        dur = max_scroll * MARQUEE_MS_PER_PX
        seq = QSequentialAnimationGroup(self)
        seq.addAnimation(self._pos_anim(0, -max_scroll, dur))
        seq.addAnimation(QPauseAnimation(MARQUEE_PAUSE_MS))
        seq.addAnimation(self._pos_anim(-max_scroll, 0, dur))
        seq.addAnimation(QPauseAnimation(MARQUEE_PAUSE_MS))
        seq.setLoopCount(-1)
        seq.start()
        self._marquee_seq = seq

    def _pos_anim(self, x0: int, x1: int, dur: int) -> QPropertyAnimation:
        anim = QPropertyAnimation(self._marquee_lbl, b"pos")
        anim.setStartValue(QPoint(x0, 0))
        anim.setEndValue(QPoint(x1, 0))
        anim.setDuration(dur)
        return anim
