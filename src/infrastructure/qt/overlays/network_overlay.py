"""Full-screen overlay showing the current network connection details.

Read-only: renders the domain-composed `view.info_lines(status)` as a label
grid, dismissed with A/B/Esc. Mirrors `VolumeOverlay` — a `BaseOverlay` managing
its own layer-shell surface and pad lifetime. All wording and which rows appear
is decided in `domain.network.view`; this only lays the rows out.
"""

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.network import view
from domain.network.status import NetworkStatus
from domain.shared.feedback import Cue, Feedback
from .base_overlay import BaseOverlay


class NetworkOverlay(BaseOverlay):
    """Centred card listing the active connection's details."""

    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        status: NetworkStatus,
        feedback: Feedback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(560)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(22)

        # Title — icon reflects the current kind.
        title_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(view.icon_for(status.kind), color="white").pixmap(30, 30))
        icon_lbl.setStyleSheet("background: transparent;")
        title = QLabel(view.title())
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Detail rows (label : value), composed by the domain.
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        for r, (label, value) in enumerate(view.info_lines(status)):
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 16px; color: #9aa0aa; background: transparent;")
            val = QLabel(value)
            val.setStyleSheet("font-size: 16px; color: white; background: transparent;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(lbl, r, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(val, r, 1)
        layout.addLayout(grid)

        hint = QLabel("A / B / Esc")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #888; background: transparent;")
        layout.addWidget(hint)

        outer.addWidget(card)

        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Input ────────────────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event in (Event.SELECT, Event.CANCEL, Event.CLOSE):
            self._close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape,
        ):
            self._close()

    def _on_outside_click(self) -> None:
        self._close()

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self.closed.emit()
