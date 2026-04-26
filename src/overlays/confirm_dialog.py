import logging
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QWidget,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from ui import styles
from .base_overlay import BaseOverlay

logger = logging.getLogger(__name__)


class ConfirmDialog(BaseOverlay):
    """
    Fullscreen overlay with a confirmation question.
    Registers its own handler in GamepadManager for its lifetime.
    """

    def __init__(
        self,
        question: str,
        on_confirmed: Callable[[], None],
        on_cancelled: Callable[[], None],
        gamepad: GamepadWatcher,
        parent: QWidget | None = None,
    ):
        super().__init__(gamepad, self._handle_pad, parent)
        self._on_confirmed = on_confirmed
        self._on_cancelled = on_cancelled
        self._focus_yes    = True

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

        lbl = QLabel(question)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 26px; color: white; background: transparent;")
        layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        self._btn_yes = QPushButton("✔  " + self.tr("Yes"))
        self._btn_no  = QPushButton("✘  " + self.tr("No"))
        for btn in (self._btn_yes, self._btn_no):
            btn.setMinimumSize(200, 80)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_yes.clicked.connect(self._confirm)
        self._btn_no.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_yes)
        btn_row.addWidget(self._btn_no)
        layout.addLayout(btn_row)

        styles.apply_card_shadow(card)

        outer.addWidget(card)
        self._refresh_buttons()

        sound_player.play("popup_open")
        self._show()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == "select":
            self._confirm() if self._focus_yes else self._cancel()
        elif event in ("cancel", "close"):
            self._cancel()
        elif event in ("left", "right"):
            self._focus_yes = not self._focus_yes
            self._refresh_buttons()
            sound_player.play("cursor")

    # ── Keyboard ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm() if self._focus_yes else self._cancel()
        elif event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._focus_yes = not self._focus_yes
            self._refresh_buttons()

    # ── Actions ────────────────────────────────────────────────────────────

    def _confirm(self) -> None:
        if self._close():
            sound_player.play("select")
            self._on_confirmed()

    def _cancel(self) -> None:
        if self._close():
            sound_player.play("popup_close")
            self._on_cancelled()

    def _close(self) -> bool:
        if self._closed:
            return False
        logger.info("ConfirmDialog._close() – hiding the dialog")
        self._closed = True
        self._gamepad.pop_handler(self._handler)
        self.hide()
        self.deleteLater()
        return True

    def force_close(self) -> None:
        """Force close (e.g. when the application ended from outside)."""
        logger.warning("ConfirmDialog.force_close() – forcing to close the dialog")
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handler)
        self.hide()
        self.deleteLater()

    def _refresh_buttons(self) -> None:
        self._btn_yes.setStyleSheet(
            styles.dialog_focused() if self._focus_yes else styles.dialog_idle()
        )
        self._btn_no.setStyleSheet(
            styles.dialog_idle() if self._focus_yes else styles.dialog_focused()
        )
