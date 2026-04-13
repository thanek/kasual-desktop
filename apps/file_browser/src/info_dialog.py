from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QGraphicsDropShadowEffect,
)


class InfoDialog(QWidget):
    """
    Fullscreen overlay with a single message and OK button.
    The look is consistent with Kasual Desktop InfoDialog.
    Closable with Enter, Escape or button pressed.
    """

    def __init__(self, message: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150);")

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setStyleSheet("background-color: #2e3440; border-radius: 12px;")
        card.setFixedWidth(680)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(36)

        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 26px; color: white; background: transparent;")
        layout.addWidget(lbl)

        btn = QPushButton("✔  " + self.tr("OK"))
        btn.setMinimumSize(200, 80)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet("""
            QPushButton {
                font-size: 22px;
                padding: 14px 24px;
                background-color: #88c0d0;
                color: black;
                border-radius: 6px;
                border: 2px solid white;
            }
        """)
        btn.clicked.connect(self._close)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setBlurRadius(40)
        card.setGraphicsEffect(shadow)

        outer.addWidget(card)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._close()

    def _close(self) -> None:
        self.hide()
        self.deleteLater()

    @staticmethod
    def show_message(message: str, parent: QWidget | None = None) -> None:
        dlg = InfoDialog(message, parent)
        dlg.showFullScreen()
        dlg.activateWindow()
        dlg.setFocus()
