from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QWidget,
)

from domain.input.vocabulary import Event
from infrastructure.audio import sound_player
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.ui import styles
from .base_overlay import BaseOverlay


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

        card = self.build_card(680)

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

        outer.addWidget(card)
        self._refresh_buttons()

        sound_player.play("popup_open")
        self._show()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.SELECT:
            self._confirm() if self._focus_yes else self._cancel()
        elif event in (Event.CANCEL, Event.CLOSE):
            self._cancel()
        elif event in (Event.LEFT, Event.RIGHT):
            self._focus_yes = not self._focus_yes
            self._refresh_buttons()
            sound_player.play("cursor")

    # ── Keyboard ───────────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._cancel()

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
        if self._dismiss(sound=Event.SELECT):
            self._on_confirmed()

    def _cancel(self) -> None:
        if self._dismiss(sound="popup_close"):
            self._on_cancelled()

    def _refresh_buttons(self) -> None:
        self._btn_yes.setStyleSheet(
            styles.dialog_focused() if self._focus_yes else styles.dialog_idle()
        )
        self._btn_no.setStyleSheet(
            styles.dialog_idle() if self._focus_yes else styles.dialog_focused()
        )
