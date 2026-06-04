"""Top bar widget: date/clock readout and the row of system-action buttons."""

from datetime import datetime

import qtawesome as qta
from PyQt6.QtCore import Qt, QLocale, QTimer, QSize, pyqtSignal
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QLabel

from system.system_actions import ACTIONS
from ui import styles

BTN_SIZE    = 56
BTN_SPACING = 14


class TopBar(QWidget):
    """Floating top bar — clock on the left/centre, action buttons on the right.

    Owns its own clock timer and action buttons. Navigation state (which button
    is focused) lives in the Desktop coordinator; the bar only renders the
    highlight it is told to via :meth:`set_selected` and reports clicks through
    :attr:`action_triggered`.
    """

    action_triggered = pyqtSignal(str)   # emits the action_type of the clicked button
    button_hovered   = pyqtSignal(int)   # emits the index of the hovered button

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 0)
        outer.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("topbar")
        bar.setFixedHeight(80)
        bar.setStyleSheet(
            "#topbar {"
            "  background-color: rgba(15, 17, 25, 210);"
            "  border: 1px solid black;"
            "  border-radius: 12px;"
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

        self._colors = [a["color"] for a in ACTIONS.values()]
        self._buttons: list[QPushButton] = []
        btn_area = QWidget()
        btn_area.setFixedWidth(btns_total)
        btn_area.setStyleSheet("background: transparent;")
        btn_layout = QHBoxLayout(btn_area)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(BTN_SPACING)

        def _bind_hover(btn: QPushButton, idx: int) -> None:
            def _enter(event) -> None:
                QPushButton.enterEvent(btn, event)
                self.button_hovered.emit(idx)
            btn.enterEvent = _enter

        for i, (action_type, action) in enumerate(ACTIONS.items()):
            btn = QPushButton()
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setIcon(qta.icon(action["icon"], color="white"))
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(styles.topbar_normal(action["color"]))
            btn.clicked.connect(lambda _, t=action_type: self.action_triggered.emit(t))
            _bind_hover(btn, i)
            btn_layout.addWidget(btn)
            self._buttons.append(btn)
        layout.addWidget(btn_area)

        self._update_clock()
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(1000)

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._buttons)

    def set_selected(self, index: int | None) -> None:
        """Highlight the button at *index*, or clear all if None."""
        for i, btn in enumerate(self._buttons):
            if i == index:
                btn.setStyleSheet(styles.topbar_selected())
            else:
                btn.setStyleSheet(styles.topbar_normal(self._colors[i]))

    def trigger(self, index: int) -> None:
        """Activate the button at *index* (as if clicked)."""
        self._buttons[index].click()

    # ── Clock ───────────────────────────────────────────────────────────────

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
        # QLocale numbers days 1=Monday … 7=Sunday, datetime.weekday() 0…6
        day   = locale.dayName(now.weekday() + 1, QLocale.FormatType.LongFormat)
        month = locale.monthName(now.month, QLocale.FormatType.ShortFormat)
        self._date_lbl.setText(f"{day}  {now.day:02d} {month}. {now.year}")
        self._lbl_h.setText(now.strftime("%H"))
        self._lbl_m.setText(now.strftime("%M"))
        self._lbl_s.setText(now.strftime("%S"))
