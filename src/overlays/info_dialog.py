import logging
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QVBoxLayout, QWidget,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from ui import styles
from .base_overlay import BaseOverlay

logger = logging.getLogger(__name__)


class InfoDialog(BaseOverlay):
    """
    Fullscreen overlay displaying an informational message with a single OK button.
    """

    def __init__(
        self,
        message: str,
        on_confirmed: Callable[[], None],
        gamepad: GamepadWatcher,
        parent: QWidget | None = None,
    ):
        super().__init__(gamepad, self._handle_pad, parent)
        self._on_confirmed = on_confirmed

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setStyleSheet(
            f"background-color: {styles.COLOR_CARD_BG}; border-radius: {styles.CARD_RADIUS_PX}px;"
        )
        card.setFixedWidth(680)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(36)

        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 26px; color: white; background: transparent;")
        layout.addWidget(lbl)

        self._btn_ok = QPushButton("✔  " + self.tr("OK"))
        self._btn_ok.setMinimumSize(200, 80)
        self._btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_ok.setStyleSheet(styles.dialog_focused())
        self._btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self._btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)

        styles.apply_card_shadow(card)

        outer.addWidget(card)

        sound_player.play("popup_open")
        self._show()

    def _handle_pad(self, event: str) -> None:
        if event in ("select", "cancel", "close"):
            self._confirm()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._confirm()

    def _confirm(self) -> None:
        if self._close():
            sound_player.play("select")
            self._on_confirmed()

    def _close(self) -> bool:
        if self._closed:
            return False
        logger.info("InfoDialog._close()")
        self._closed = True
        self._gamepad.pop_handler(self._handler)
        self.hide()
        self.deleteLater()
        return True

    def force_close(self) -> None:
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handler)
        self.hide()
        self.deleteLater()
