"""Top bar widget for Windows - clock and system action buttons."""

from datetime import datetime
from typing import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, QLocale, QTimer, QSize, pyqtSignal
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QLabel

from domain.system.actions import ACTIONS

BTN_SIZE    = 56
BTN_SPACING = 14

COLOR_ACCENT = "#88c0d0"


def _topbar_normal(color: str) -> str:
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: 13px;
        }}
    """


def _topbar_selected() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: black;
            border: 3px solid white;
            border-radius: 13px;
        }}
    """


class WindowsTopBar(QWidget):
    """Top bar with clock and 8 action buttons - mirrors Linux TopBar."""

    action_triggered = pyqtSignal(str)
    button_hovered   = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._buttons: list[QPushButton] = []
        self._badges: dict[str, QLabel] = {}
        self._action_keys: list[str] = list(ACTIONS)
        self._colors: list[str] = [action.color for action in ACTIONS.values()]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 0)
        outer.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("topbar")
        bar.setFixedHeight(80)
        bar.setStyleSheet(
            "#topbar {\n"
            "  background-color: rgba(15, 17, 25, 210);\n"
            "  border: 1px solid black;\n"
            "  border-radius: 12px;\n"
            "}"
        )
        outer.addWidget(bar)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        btns_total = len(ACTIONS) * BTN_SIZE + (len(ACTIONS) - 1) * BTN_SPACING

        spacer = QWidget()
        spacer.setFixedWidth(btns_total)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

        layout.addStretch(1)
        self._build_clock(layout)
        layout.addStretch(1)

        btn_area = QWidget()
        btn_area.setFixedWidth(btns_total)
        btn_area.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_area)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(BTN_SPACING)

        for i, action_type in enumerate(self._action_keys):
            view = ACTIONS[action_type]
            btn = QPushButton()
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            try:
                btn.setIcon(qta.icon(view.icon, color="white"))
            except Exception:
                btn.setIcon(qta.icon("fa5s.desktop", color="white"))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(_topbar_normal(view.color))
            btn.clicked.connect(lambda _, t=action_type: self.action_triggered.emit(t))
            self._bind_hover(btn, i)
            btn_layout.addWidget(btn)
            self._buttons.append(btn)
        layout.addWidget(btn_area)

        self._update_clock()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

    def _bind_hover(self, btn: QPushButton, idx: int) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            self.button_hovered.emit(idx)
        btn.enterEvent = _enter

    @property
    def count(self) -> int:
        return len(self._buttons)

    def set_selected(self, index: int | None) -> None:
        for i, btn in enumerate(self._buttons):
            if i == index:
                btn.setStyleSheet(_topbar_selected())
            else:
                btn.setStyleSheet(_topbar_normal(self._colors[i]))

    def trigger(self, index: int) -> None:
        self._buttons[index].click()

    def set_action_icon(self, action_key: str, glyph: str) -> None:
        if action_key not in self._action_keys:
            return
        btn = self._buttons[self._action_keys.index(action_key)]
        try:
            btn.setIcon(qta.icon(glyph, color="white"))
        except Exception:
            pass

    def set_badge(self, action_key: str, count: int) -> None:
        if action_key not in self._action_keys:
            return
        btn = self._buttons[self._action_keys.index(action_key)]
        badge = self._badges.get(action_key)
        if badge is None:
            badge = QLabel(btn)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._badges[action_key] = badge

        if count <= 0:
            badge.hide()
            return

        badge.setText(str(count) if count <= 9 else "9+")
        badge.setStyleSheet(
            "background-color: #bf616a; color: white; font-size: 10px;"
            " font-weight: bold; border-radius: 10px;"
        )
        badge.setFixedSize(20, 20)
        badge.move(BTN_SIZE - 20 - 2, 2)
        badge.show()
        badge.raise_()

    def _build_clock(self, layout: QHBoxLayout) -> None:
        lbl_style = "font-size: 26px; color: white; background: transparent;"
        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(lbl_style)
        layout.addWidget(self._date_lbl)

        layout.addSpacing(18)

        def clock_part(w: int) -> QLabel:
            l = QLabel()
            l.setStyleSheet(lbl_style)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setFixedWidth(w)
            return l

        def sep() -> QLabel:
            l = QLabel(":")
            l.setStyleSheet(lbl_style)
            return l

        self._lbl_h = clock_part(38)
        self._lbl_m = clock_part(38)
        self._lbl_s = clock_part(38)
        for w in (self._lbl_h, sep(), self._lbl_m, sep(), self._lbl_s):
            layout.addWidget(w)

    def _update_clock(self) -> None:
        now    = datetime.now()
        locale = QLocale.system()
        day    = locale.dayName(now.weekday() + 1, QLocale.FormatType.LongFormat)
        month  = locale.monthName(now.month, QLocale.FormatType.ShortFormat)
        self._date_lbl.setText(f"{day}  {now.day:02d} {month}. {now.year}")
        self._lbl_h.setText(now.strftime("%H"))
        self._lbl_m.setText(now.strftime("%M"))
        self._lbl_s.setText(now.strftime("%S"))