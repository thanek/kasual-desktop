from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QWidget,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.shared.feedback import Cue, Feedback
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
        gamepad: PadControl,
        feedback: Feedback,
        parent: QWidget | None = None,
    ):
        super().__init__(gamepad, self._handle_pad, feedback, parent)
        self._on_confirmed = on_confirmed
        self._on_cancelled = on_cancelled
        self._cursor = MenuCursor(
            count=lambda: 2,
            render=self._refresh_buttons,
            on_activate=self._on_activate,
            on_dismiss=self._cancel,
            feedback=feedback,
            wrap=True,
        )

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
        self._cursor.reset(0)

        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Focus state (backed by cursor index) ───────────────────────────────

    @property
    def _focus_yes(self) -> bool:
        return self._cursor.index == 0

    @_focus_yes.setter
    def _focus_yes(self, value: bool) -> None:
        self._cursor.index = 0 if value else 1

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.LEFT:
            self._cursor.handle_pad(Event.UP)
        elif event == Event.RIGHT:
            self._cursor.handle_pad(Event.DOWN)
        else:
            self._cursor.handle_pad(event)

    # ── Keyboard ───────────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._cancel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cursor.handle_pad(Event.SELECT)
        elif key == Qt.Key.Key_Escape:
            self._cursor.handle_pad(Event.CANCEL)
        elif key == Qt.Key.Key_Left:
            self._cursor.handle_pad(Event.UP)
        elif key == Qt.Key.Key_Right:
            self._cursor.handle_pad(Event.DOWN)

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_activate(self, index: int) -> None:
        if index == 0:
            self._confirm()
        else:
            self._cancel()

    def _confirm(self) -> None:
        if self._dismiss(sound=Cue.SELECT):
            self._on_confirmed()

    def _cancel(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._on_cancelled()

    def _refresh_buttons(self, index: int) -> None:
        self._btn_yes.setStyleSheet(
            styles.dialog_focused() if index == 0 else styles.dialog_idle()
        )
        self._btn_no.setStyleSheet(
            styles.dialog_idle() if index == 0 else styles.dialog_focused()
        )
