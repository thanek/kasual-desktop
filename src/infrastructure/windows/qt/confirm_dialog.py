"""Confirm dialog stub for Windows."""

import logging
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QWidget

logger = logging.getLogger(__name__)


class ConfirmDialog(QDialog):
    """Stub Confirm dialog - shows question with Yes/No, calls callbacks."""

    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        question: str,
        on_confirmed: Callable[[], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_confirmed = on_confirmed
        self._on_cancelled = on_cancelled

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.setSpacing(16)

        card = QWidget()
        card.setStyleSheet("""
            background-color: rgba(40, 40, 55, 250);
            border: 1px solid #5e81ac;
            border-radius: 12px;
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(16)

        self._question_lbl = QLabel(question)
        self._question_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._question_lbl.setStyleSheet("font-size: 18px; color: white;")
        card_layout.addWidget(self._question_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        btn_yes = QPushButton("Yes")
        btn_yes.setFixedWidth(100)
        btn_yes.setStyleSheet("""
            QPushButton {
                background-color: #5e81ac;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #81a1c1; }
        """)
        btn_yes.clicked.connect(self._on_yes)
        btn_row.addWidget(btn_yes)

        btn_no = QPushButton("No")
        btn_no.setFixedWidth(100)
        btn_no.setStyleSheet("""
            QPushButton {
                background-color: #4c566a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #5e81ac; }
        """)
        btn_no.clicked.connect(self._on_no)
        btn_row.addWidget(btn_no)

        card_layout.addLayout(btn_row)
        layout.addWidget(card)

        logger.info("ConfirmDialog shown: %s", question)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return:
            self._on_yes()
        elif event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_B):
            self._on_no()
        super().keyPressEvent(event)

    def _on_yes(self) -> None:
        logger.info("ConfirmDialog confirmed")
        if self._on_confirmed:
            self._on_confirmed()
        self.accept()
        self.confirmed.emit()

    def _on_no(self) -> None:
        logger.info("ConfirmDialog cancelled")
        if self._on_cancelled:
            self._on_cancelled()
        self.reject()
        self.cancelled.emit()

    def cancel(self) -> None:
        self._on_no()

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass