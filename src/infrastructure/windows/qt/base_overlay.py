"""Base overlay class for Windows overlays."""

import logging
from abc import abstractmethod

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout

logger = logging.getLogger(__name__)


class BaseOverlay(QWidget):
    """Stub base class for Windows overlays (Volume, Brightness, Network, Notifications)."""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._build_content(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 40, 240);
                color: white;
            }
        """)

    @abstractmethod
    def _build_content(self, layout: QVBoxLayout) -> None:
        pass

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_B):
            self._on_close()
        super().keyPressEvent(event)

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()

    def show_overlay(self) -> None:
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self.hide()