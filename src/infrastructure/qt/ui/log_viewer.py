import logging
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit, QLabel,
)

logger = logging.getLogger(__name__)

_STYLE = """
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
}
QPlainTextEdit {
    background-color: #0d1117;
    color: #c9d1d9;
    border: none;
    font-size: 12px;
}
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #30363d;
}
"""


class LogViewer(QWidget):
    """Window displaying log file contents with auto-scroll to the bottom."""

    def __init__(self, log_file: str, parent=None):
        super().__init__(parent)
        self._log_file  = log_file
        self._last_size = -1

        self.setWindowTitle(self.tr("Kasual – Logs"))
        self.resize(900, 500)
        self.setStyleSheet(_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(5000)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self._text.setFont(mono)
        layout.addWidget(self._text)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)

        self._refresh()

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(
            "background-color: #161b22; border-bottom: 1px solid #30363d;"
        )
        header.setFixedHeight(40)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 0, 12, 0)

        lbl = QLabel(f"📄 {os.path.basename(self._log_file)}")
        lbl.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        layout.addWidget(lbl)
        layout.addStretch()

        btn = QPushButton(self.tr("Clear"))
        btn.clicked.connect(self._clear_log)
        layout.addWidget(btn)

        return header

    # ── Refreshing ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not os.path.exists(self._log_file):
            return
        size = os.path.getsize(self._log_file)
        if size == self._last_size:
            return
        self._last_size = size
        try:
            with open(self._log_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._text.setPlainText(content)
            self._scroll_to_bottom()
        except OSError as e:
            logger.warning("Could not read log file: %s", e)

    def _scroll_to_bottom(self) -> None:
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_log(self) -> None:
        try:
            open(self._log_file, "w").close()
            self._text.clear()
            self._last_size = 0
        except OSError as e:
            logger.warning("Could not clear log file: %s", e)

    # ── Show with forced refresh ──────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._last_size = -1
        self._refresh()
