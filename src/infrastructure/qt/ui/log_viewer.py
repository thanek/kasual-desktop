import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit, QLabel,
)

from domain.shared.log_provider import LogProvider

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
    """Window displaying log contents with auto-scroll to the bottom.

    Pure presentation: it polls a domain `LogProvider` for fresh text and
    renders it; the provider owns *what* to serve and when (change detection),
    and where the bytes come from (the injected source).
    """

    def __init__(self, provider: LogProvider, parent=None):
        super().__init__(parent)
        self._provider = provider

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

        lbl = QLabel(f"📄 {self._provider.name}")
        lbl.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        layout.addWidget(lbl)
        layout.addStretch()

        btn = QPushButton(self.tr("Clear"))
        btn.clicked.connect(self._clear_log)
        layout.addWidget(btn)

        return header

    # ── Refreshing ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        content = self._provider.poll()
        if content is None:
            return
        self._text.setPlainText(content)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_log(self) -> None:
        self._provider.clear()
        self._text.clear()

    # ── Show with forced refresh ──────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._provider.invalidate()
        self._refresh()
