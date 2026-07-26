"""Qt PreflightView: the enable prompt and the manual-setup instructions shown
before the session comes up, when the GNOME helper extension isn't answering yet.
"""

from collections.abc import Callable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.preflight.extension_gate import ExtensionState, PreflightView
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Keyboard
from .base_overlay import BaseOverlay

_INSTALL_HINT = "gnome-extensions enable kasual-helper@consoledesktop.org"

_CARD_WIDTH = 880
_CARD_MARGIN = 48
_TEXT_PX = 24


class _PreflightDialog(BaseOverlay):
    """A message over a row of choices. The last choice is what Cancel and an
    outside click resolve to, so it is always the way out."""

    def __init__(
        self,
        message: str,
        choices: Sequence[tuple[str, Callable[[], None]]],
        gamepad: PadControl,
        feedback: Feedback,
        *,
        dismissable: bool,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, keyboard=Keyboard.ON_DEMAND)
        self._actions = [action for _, action in choices]
        self._dismissable = dismissable
        self._cursor = MenuCursor(
            count=lambda: len(self._actions),
            render=self._refresh_buttons,
            on_activate=self._activate,
            on_dismiss=self._dismiss_last,
            feedback=feedback,
            wrap=True,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN)
        layout.setSpacing(36)

        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        font = label.font()
        font.setPixelSize(_TEXT_PX)
        label.setFont(font)
        label.setStyleSheet("color: white; background: transparent;")
        label.setMinimumHeight(label.heightForWidth(_CARD_WIDTH - 2 * _CARD_MARGIN))
        layout.addWidget(label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        self._buttons = []
        for i, (label_text, _) in enumerate(choices):
            btn = QPushButton(label_text)
            btn.setMinimumSize(200, 80)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._bind_hover(btn, i)
            btn.clicked.connect(lambda _checked=False, index=i: self._activate(index))
            btn_row.addWidget(btn)
            self._buttons.append(btn)
        layout.addLayout(btn_row)

        outer.addWidget(card)
        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    def _bind_hover(self, btn: QPushButton, index: int) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            self._cursor.hover(index)
        btn.enterEvent = _enter

    def _handle_pad(self, event: str) -> None:
        if event == Event.LEFT:
            self._cursor.handle_pad(Event.UP)
        elif event == Event.RIGHT:
            self._cursor.handle_pad(Event.DOWN)
        else:
            self._cursor.handle_pad(event)

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

    def _on_outside_click(self) -> None:
        if self._dismissable:
            self._dismiss_last()

    def _activate(self, index: int) -> None:
        if index == len(self._actions) - 1:
            self._dismiss_last()
        elif self._dismiss(sound=Cue.SELECT):
            self._actions[index]()

    def _dismiss_last(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._actions[-1]()

    def _refresh_buttons(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            role = "primary" if i == 0 else "secondary"
            styles.style_dialog_button(btn, role=role, focused=index == i)


class QtPreflightView(PreflightView):
    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback
        self._current: _PreflightDialog | None = None

    def ask_enable(
        self, on_accept: Callable[[], None], on_decline: Callable[[], None]
    ) -> None:
        self._present(
            translate(
                "Kasual Desktop",
                "Kasual Desktop needs its GNOME Shell helper extension to manage "
                "windows.\n\nEnable it now?",
            ),
            [(translate("Kasual Desktop", "Enable"), on_accept),
             (translate("Kasual Desktop", "Not now"), on_decline)],
            dismissable=True,
        )

    def show_instructions(
        self,
        state: ExtensionState,
        on_retry: Callable[[], None],
        on_quit: Callable[[], None],
        on_logout: Callable[[], None] | None = None,
    ) -> None:
        if state is ExtensionState.ABSENT:
            body = translate(
                "Kasual Desktop",
                "The Kasual Helper GNOME Shell extension isn't installed. Install the "
                "Kasual Desktop package, then enable it with:",
            )
        elif state is ExtensionState.UNLOADED:
            body = translate(
                "Kasual Desktop",
                "The Kasual Helper GNOME Shell extension is installed, but this GNOME "
                "session started before it and cannot load it. Log out and back in, "
                "then enable it with:",
            )
        else:
            body = translate(
                "Kasual Desktop",
                "Kasual Desktop couldn't enable its GNOME Shell helper extension. "
                "Enable it manually with:",
            )
        message = f"{body}\n\n{_INSTALL_HINT}"
        if on_logout is not None:
            choices = [(translate("Kasual Desktop", "Log out"), on_logout)]
        else:
            message += "\n\n" + translate("Kasual Desktop", "then retry.")
            choices = [(translate("Kasual Desktop", "Retry"), on_retry)]
        choices.append((translate("Kasual Desktop", "Quit"), on_quit))
        self._present(message, choices, dismissable=False)

    def _present(
        self,
        message: str,
        choices: Sequence[tuple[str, Callable[[], None]]],
        *,
        dismissable: bool,
    ) -> None:
        self._current = _PreflightDialog(
            message, choices, self._gamepad, self._feedback, dismissable=dismissable,
        )
