"""About box: a centred layer-shell card with app/author/license info.

Triggered from the system-tray menu. Like the other overlays it is a standalone
wlr-layer-shell surface; it closes on the Close button, gamepad SELECT/CANCEL,
Esc/Enter, or a click outside the card.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout

import qtawesome as qta

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.shared.feedback import Cue, Feedback
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Keyboard
from .base_overlay import BaseOverlay

_GITHUB_URL = "https://github.com/thanek/kasual-desktop"
_AUTHOR = "thanek"
_AUTHOR_EMAIL = "xis@schowek.net"
_LICENSE_NAME = "GNU General Public License v3.0"
_LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


class AboutOverlay(BaseOverlay):
    """Read-only info dialog. Single action: close."""

    def __init__(self, version: str, gamepad: PadControl, feedback: Feedback) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, keyboard=Keyboard.ON_DEMAND)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(560)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 44, 48, 44)
        layout.setSpacing(18)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(qta.icon("fa5s.gamepad", color=styles.COLOR_ACCENT).pixmap(72, 72))
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)

        title = QLabel("Kasual Desktop")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: white; background: transparent;")
        layout.addWidget(title)

        ver = QLabel(self.tr("Version {0}").format(version))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size: 16px; color: #d8dee9; background: transparent;")
        layout.addWidget(ver)

        info = QLabel(
            f'<div style="line-height: 160%;">'
            f'{self.tr("Author")}: {_AUTHOR} &lt;<a href="mailto:{_AUTHOR_EMAIL}" '
            f'style="color: {styles.COLOR_ACCENT};">{_AUTHOR_EMAIL}</a>&gt;<br>'
            f'{self.tr("License")}: <a href="{_LICENSE_URL}" '
            f'style="color: {styles.COLOR_ACCENT};">{_LICENSE_NAME}</a><br>'
            f'<a href="{_GITHUB_URL}" style="color: {styles.COLOR_ACCENT};">{_GITHUB_URL}</a>'
            f'</div>'
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setOpenExternalLinks(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 16px; color: #e5e9f0; background: transparent;")
        layout.addWidget(info)

        self._btn_close = QPushButton(self.tr("Close"))
        self._btn_close.setMinimumSize(200, 64)
        self._btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_close.setStyleSheet(styles.dialog_focused())
        self._btn_close.clicked.connect(self._close)
        layout.addWidget(self._btn_close, alignment=Qt.AlignmentFlag.AlignCenter)

        outer.addWidget(card)

        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    def _close(self) -> None:
        self._dismiss(sound=Cue.POPUP_CLOSE)

    def _on_outside_click(self) -> None:
        self._close()

    def _handle_pad(self, event: str) -> None:
        if event in (Event.SELECT, Event.CANCEL, Event.CLOSE):
            self._close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._close()
