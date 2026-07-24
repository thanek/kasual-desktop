"""Qt PreflightView: the enable prompt and the manual-setup instructions shown
before the session comes up, when the GNOME helper extension isn't answering yet.
"""

from collections.abc import Callable

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
_LAYER_SHELL_HINT = "layer-shell-qt — built against Qt 6"
_CARD_MARGIN = 48


class _PreflightDialog(BaseOverlay):
    def __init__(
        self,
        message: str,
        primary_label: str,
        secondary_label: str,
        on_primary: Callable[[], None],
        on_secondary: Callable[[], None],
        gamepad: PadControl,
        feedback: Feedback,
        *,
        dismissable: bool,
        card_width: int = 680,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, keyboard=Keyboard.ON_DEMAND)
        self._on_primary = on_primary
        self._on_secondary = on_secondary
        self._dismissable = dismissable
        self._cursor = MenuCursor(
            count=lambda: 2,
            render=self._refresh_buttons,
            on_activate=self._activate,
            on_dismiss=self._dismiss_secondary,
            feedback=feedback,
            wrap=True,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(card_width)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(_CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN)
        layout.setSpacing(36)

        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        # A wrapped QLabel's sizeHint is one line tall, so the layout builds the card
        # too short and clips the message. The card's width is fixed and known here,
        # so ask for the height the wrapped text actually needs at that width —
        # after polishing, or the question is answered for the default font rather
        # than the larger one the style sheet above sets.
        label.ensurePolished()
        label.setMinimumHeight(label.heightForWidth(card_width - 2 * _CARD_MARGIN))
        layout.addWidget(label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        self._btn_primary = QPushButton(primary_label)
        self._btn_secondary = QPushButton(secondary_label)
        for i, btn in enumerate((self._btn_primary, self._btn_secondary)):
            btn.setMinimumSize(200, 80)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._bind_hover(btn, i)
        self._btn_primary.clicked.connect(lambda: self._activate(0))
        self._btn_secondary.clicked.connect(lambda: self._activate(1))
        btn_row.addWidget(self._btn_primary)
        btn_row.addWidget(self._btn_secondary)
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
            self._dismiss_secondary()

    def _activate(self, index: int) -> None:
        if index == 0:
            if self._dismiss(sound=Cue.SELECT):
                self._on_primary()
        else:
            self._dismiss_secondary()

    def _dismiss_secondary(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._on_secondary()

    def _refresh_buttons(self, index: int) -> None:
        styles.style_dialog_button(self._btn_primary, role="primary", focused=index == 0)
        styles.style_dialog_button(self._btn_secondary, role="secondary", focused=index == 1)


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
            translate("Kasual Desktop", "Enable"),
            translate("Kasual Desktop", "Not now"),
            on_accept, on_decline, dismissable=True,
        )

    def show_instructions(
        self,
        state: ExtensionState,
        on_retry: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        if state is ExtensionState.ABSENT:
            body = translate(
                "Kasual Desktop",
                "The Kasual Helper GNOME Shell extension isn't installed. Install the "
                "Kasual Desktop package, then enable it with:",
            )
        else:
            body = translate(
                "Kasual Desktop",
                "Kasual Desktop couldn't enable its GNOME Shell helper extension. "
                "Enable it manually with:",
            )
        message = f"{body}\n\n{_INSTALL_HINT}\n\n" + translate("Kasual Desktop", "then retry.")
        self._present(
            message,
            translate("Kasual Desktop", "Retry"),
            translate("Kasual Desktop", "Quit"),
            on_retry, on_quit, dismissable=False,
        )

    def show_missing_layer_shell(
        self, on_continue: Callable[[], None], on_quit: Callable[[], None]
    ) -> None:
        message = "\n\n".join((
            translate(
                "Kasual Desktop",
                "Kasual Desktop places its interface with wlr-layer-shell, and this "
                "session has none it can use. Without it the compositor decides "
                "where every part lands, and the interface comes up scattered.",
            ),
            translate("Kasual Desktop", "Install, then start again:"),
            _LAYER_SHELL_HINT,
        ))
        self._present(
            message,
            translate("Kasual Desktop", "Continue anyway"),
            translate("Kasual Desktop", "Quit"),
            on_continue, on_quit, dismissable=False,
            card_width=980,
        )

    def _present(
        self,
        message: str,
        primary_label: str,
        secondary_label: str,
        on_primary: Callable[[], None],
        on_secondary: Callable[[], None],
        *,
        dismissable: bool,
        card_width: int = 680,
    ) -> None:
        self._current = _PreflightDialog(
            message, primary_label, secondary_label,
            on_primary, on_secondary,
            self._gamepad, self._feedback, dismissable=dismissable,
            card_width=card_width,
        )
