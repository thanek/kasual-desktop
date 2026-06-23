"""Full-screen overlay showing the current network connection details.

Renders the domain-composed `view.info_lines(status)` as a label grid, plus a
single connect/disconnect toggle whose label, action and enabled-state are all
decided by `view.connect_button` (the domain — this only lays it out and relays
the press onto the injected `NetworkControl`). Mirrors `VolumeOverlay`: a
`BaseOverlay` managing its own layer-shell surface and pad lifetime. Dismissed
with B/Esc; A activates the toggle when it is enabled.
"""

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.network import view
from domain.network.control import NetworkControl
from domain.network.status import NetworkStatus
from domain.shared.feedback import Cue, Feedback
from infrastructure.common.qt.ui import styles
from .base_overlay import BaseOverlay


class NetworkOverlay(BaseOverlay):
    """Centred card listing the active connection's details + a connect toggle."""

    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        status: NetworkStatus,
        control: NetworkControl,
        feedback: Feedback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent)
        self._control = control
        # The domain decides which action the button performs and whether it can.
        self._button = view.connect_button(status, control.can_reconnect())

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

        # Connect / disconnect toggle.
        self._btn = QPushButton(self._button.label)
        self._btn.setMinimumHeight(64)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setEnabled(self._button.enabled)
        self._btn.setStyleSheet(
            styles.dialog_focused() if self._button.enabled else _DISABLED_BUTTON
        )
        self._btn.clicked.connect(self._activate)
        layout.addWidget(self._btn)

        hint = QLabel("A / B / Esc")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #888; background: transparent;")
        layout.addWidget(hint)

        outer.addWidget(card)

        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Input ────────────────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.SELECT:
            self._activate()
        elif event in (Event.CANCEL, Event.CLOSE):
            self._close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate()
        elif key == Qt.Key.Key_Escape:
            self._close()

    def _on_outside_click(self) -> None:
        self._close()

    # ── Actions ────────────────────────────────────────────────────────────────

    def _activate(self) -> None:
        """Run the toggle's effect (if enabled) and close. A disabled button is
        inert — only B/Esc dismiss it then."""
        if not self._button.enabled:
            return
        if self._button.reconnect:
            self._control.reconnect()
        else:
            self._control.disconnect()
        if self._dismiss(sound=Cue.SELECT):
            self.closed.emit()

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self.closed.emit()


_DISABLED_BUTTON = """
    QPushButton {
        font-size: 22px;
        padding: 14px 24px;
        background-color: #3b4252;
        color: #6b7280;
        border-radius: 6px;
        border: 2px solid transparent;
    }
"""
