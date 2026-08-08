"""Qt SetupView: the checklist card every onboarding requirement is shown through.

Commands are offered for copying, never run: they need root and, where a vendor
installer is involved, the user's own answers. The buttons a recipe contributes
are the exception — those are things Kasual Desktop can do on its own behalf.
"""

import enum
from collections.abc import Callable

import qtawesome
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.setup.plan import (
    Readiness, ReadinessReport, Remedy, StatusLine, StepStatus, Verification,
)
from domain.setup.ports import SetupView, VerificationProbe
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Keyboard
from .base_overlay import BaseOverlay

_CARD_WIDTH = 960
_CARD_MARGIN = 40
_CARD_MAX_HEIGHT_RATIO = 0.9
_BUTTON_MIN_WIDTH = 150
_BUTTON_HEIGHT = 72
_COPIED_FEEDBACK_MS = 1500
_COPY_ICON = "fa5s.copy"
_COPIED_ICON = "fa5s.check-circle"
_COPY_ICON_BOX = 40
_COPY_ICON_PX = 20

_DONE_MARK = "✓"
_PENDING_MARK = "○"
_INDENT_PX = 28
_SCROLLBAR_PX = 12
_NARROWEST_TEXT_WIDTH = (
    _CARD_WIDTH - 2 * _CARD_MARGIN - _INDENT_PX - _SCROLLBAR_PX)


class _Confirmation(enum.Enum):
    UNKNOWN = "unknown"
    RUNNING = "running"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class _SetupDialog(BaseOverlay):
    """Leaving resumes startup, so only the last button — Continue, or Quit where
    the requirement blocks — and Escape do it; the backdrop keeps BaseOverlay's
    do-nothing click."""

    def __init__(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        on_abort: Callable[[], None],
        on_remedy: Callable[[Remedy], None],
        probe: VerificationProbe | None,
        gamepad: PadControl,
        feedback: Feedback,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback,
                         keyboard=Keyboard.ON_DEMAND)
        self._report = report
        self._on_recheck = on_recheck
        self._on_done = on_done
        self._on_abort = on_abort
        self._on_remedy = on_remedy
        self._probe = probe
        self._confirmation = _Confirmation.UNKNOWN
        self._buttons: list[QPushButton] = []
        self._actions: list[Callable[[], None]] = []

        self._cursor = MenuCursor(
            count=lambda: len(self._actions),
            render=self._render_buttons,
            on_activate=self._activate,
            on_dismiss=self._leave,
            feedback=feedback,
            wrap=True,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = self.build_card(_CARD_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        screen = QApplication.primaryScreen()
        if screen is not None:
            card.setMaximumHeight(
                int(screen.availableGeometry().height() * _CARD_MAX_HEIGHT_RATIO))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN)
        layout.setSpacing(14)

        self._title = self._build_title(report.subject.title)
        layout.addWidget(self._title)
        layout.addWidget(self._build_statuses_area())
        self._guidance = self._build_detail_label()
        layout.addWidget(self._guidance)
        self._notice = self._build_detail_label(muted=True)
        layout.addWidget(self._notice)
        layout.addWidget(self._build_steps_area())
        self._confirmation_status = self._build_status_label()
        layout.addWidget(self._confirmation_status)
        self._confirmation_detail = self._build_detail_label()
        layout.addWidget(self._confirmation_detail)
        layout.addLayout(self._build_buttons(report))
        outer.addWidget(card)

        self._apply(report)
        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Building ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_title(text: str) -> QLabel:
        label = _wrapped(
            f"font-size: 28px; color: {styles.COLOR_ACCENT}; font-weight: bold;"
            " background: transparent;",
            text,
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _build_status_label() -> QLabel:
        return _wrapped("")

    @staticmethod
    def _build_detail_label(*, muted: bool = False) -> QLabel:
        color = styles.COLOR_TRACK if muted else styles.COLOR_TEXT
        return _wrapped(
            f"font-size: 16px; color: {color}; background: transparent;"
            f" padding-left: {_INDENT_PX}px;")

    def _build_statuses_area(self) -> QWidget:
        self._statuses_container = QWidget()
        self._statuses_container.setStyleSheet("background: transparent;")
        self._statuses_layout = QVBoxLayout(self._statuses_container)
        self._statuses_layout.setContentsMargins(0, 0, 0, 0)
        self._statuses_layout.setSpacing(10)
        self._statuses_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        return self._statuses_container

    def _build_steps_area(self) -> QScrollArea:
        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background: transparent;")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(14)
        self._steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._steps_area = QScrollArea()
        self._steps_area.setWidget(self._steps_container)
        self._steps_area.setWidgetResizable(True)
        self._steps_area.setFrameShape(QFrame.Shape.NoFrame)
        self._steps_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._steps_area.viewport().setStyleSheet("background: transparent;")
        self._steps_area.setStyleSheet(styles.flat_scrollbar())
        return self._steps_area

    def _build_buttons(self, report: ReadinessReport) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        for remedy in report.remedies:
            self._add_button(row, remedy.label, lambda r=remedy: self._remedy(r))
        self._check_button = self._add_button(
            row, translate("Kasual Desktop", "Check again"), self._run_checks)
        self._add_button(row, self._leave_label(report), self._leave)
        return row

    @staticmethod
    def _leave_label(report: ReadinessReport) -> str:
        if report.subject.blocking:
            return translate("Kasual Desktop", "Quit")
        return translate("Kasual Desktop", "Continue")

    def _add_button(
        self, row: QHBoxLayout, text: str, action: Callable[[], None]
    ) -> QPushButton:
        index = len(self._buttons)
        button = QPushButton(text)
        button.setMinimumSize(_BUTTON_MIN_WIDTH, _BUTTON_HEIGHT)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda _checked=False, i=index: self._activate(i))
        self._bind_hover(button, index)
        row.addWidget(button)
        self._buttons.append(button)
        self._actions.append(action)
        return button

    def _bind_hover(self, button: QPushButton, index: int) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(button, event)
            self._cursor.hover(index)
        button.enterEvent = _enter

    # ── Rendering ────────────────────────────────────────────────────────────

    @staticmethod
    def _set_status(label: QLabel, text: str, *, met: bool) -> None:
        _set_text(
            label, f"{_DONE_MARK}  {text}" if met else f"{_PENDING_MARK}  {text}")
        color = styles.COLOR_RUNNING if met else styles.COLOR_TEXT
        weight = "bold" if met else "normal"
        label.setStyleSheet(
            f"font-size: 20px; color: {color}; font-weight: {weight};"
            " background: transparent;")

    def _apply(self, report: ReadinessReport) -> None:
        self._report = report
        self._rebuild_statuses(report.statuses)
        _set_text(self._guidance, self._guidance_text(report))
        self._guidance.setVisible(bool(self._guidance.text()))
        ready = report.state is Readiness.READY
        _set_text(self._notice, "" if ready else report.notice)
        self._notice.setVisible(not ready and bool(report.notice))
        self._rebuild_steps(() if ready else report.steps)
        self._render_confirmation()
        self._render_buttons(self._cursor.index)

    @staticmethod
    def _guidance_text(report: ReadinessReport) -> str:
        if report.state is Readiness.READY:
            return ""
        if report.state is Readiness.UNSUPPORTED:
            return report.subject.unsupported
        if report.subject.blocking:
            return translate(
                "Kasual Desktop",
                "Work through these steps in a terminal, then check again.",
            )
        return translate(
            "Kasual Desktop",
            "Work through these steps in a terminal, then check again. You can "
            "also continue now and come back later.",
        )

    def _rebuild_statuses(self, statuses: tuple[StatusLine, ...]) -> None:
        _clear(self._statuses_layout)
        for status in statuses:
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            layout = QVBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            label = self._build_status_label()
            self._set_status(label, status.text, met=status.met)
            layout.addWidget(label)
            if status.detail and not status.met:
                detail = self._build_detail_label()
                _set_text(detail, status.detail)
                layout.addWidget(detail)
            self._statuses_layout.addWidget(holder)
            _visible_before_measuring(holder)

    def _render_confirmation(self) -> None:
        wording = self._report.subject.verification
        if self._probe is None or wording is None:
            self._confirmation_status.setVisible(False)
            self._confirmation_detail.setVisible(False)
            return
        text, detail = self._confirmation_text(wording)
        self._set_status(self._confirmation_status, text,
                         met=self._confirmation is _Confirmation.CONFIRMED)
        self._confirmation_status.setVisible(True)
        _set_text(self._confirmation_detail, detail)
        self._confirmation_detail.setVisible(bool(detail))

    def _confirmation_text(self, wording: Verification) -> tuple[str, str]:
        if self._confirmation is _Confirmation.CONFIRMED:
            return wording.confirmed, ""
        if self._confirmation is _Confirmation.RUNNING:
            return wording.running, ""
        if self._confirmation is _Confirmation.FAILED:
            return wording.failed, wording.detail_failed
        return wording.unchecked, wording.detail_unchecked

    def _rebuild_steps(self, steps: tuple[StepStatus, ...]) -> None:
        _clear(self._steps_layout)
        for number, status in enumerate(steps, start=1):
            step = self._step_widget(number, status)
            self._steps_layout.addWidget(step)
            _visible_before_measuring(step)
        self._steps_area.setVisible(bool(steps))
        if steps:
            self._fit_steps_height()

    def _step_widget(self, number: int, status: StepStatus) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(_INDENT_PX, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        mark = _DONE_MARK if status.done else _PENDING_MARK
        color = styles.COLOR_RUNNING if status.done else styles.COLOR_ACCENT
        heading = _wrapped(
            f"font-size: 18px; font-weight: bold; color: {color};"
            " background: transparent;",
            f"{mark}  {number}. {status.step.title}",
        )
        layout.addWidget(heading)

        instruction = _wrapped(
            f"font-size: 16px; color: {styles.COLOR_TEXT}; background: transparent;",
            status.step.instruction,
        )
        layout.addWidget(instruction)

        if status.step.command:
            layout.addWidget(self._command_field(status.step.command))
        return holder

    def _command_field(self, command: str) -> QWidget:
        field = QWidget()
        field.setStyleSheet(
            f"background-color: {styles.COLOR_BG_DARK}; border-radius: 8px;")
        row = QHBoxLayout(field)
        row.setContentsMargins(14, 6, 6, 6)
        row.setSpacing(8)

        label = _wrapped(
            f"font-family: monospace; font-size: 16px; color: {styles.COLOR_ACCENT};"
            " background: transparent;",
            command,
        )
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setCursor(Qt.CursorShape.IBeamCursor)
        row.addWidget(label, stretch=1)

        copy = QPushButton()
        copy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        copy.setCursor(Qt.CursorShape.PointingHandCursor)
        copy.setFixedSize(_COPY_ICON_BOX, _COPY_ICON_BOX)
        copy.setIconSize(QSize(_COPY_ICON_PX, _COPY_ICON_PX))
        copy.setToolTip(translate("Kasual Desktop", "Copy to clipboard"))
        copy.setStyleSheet(
            "QPushButton { background: transparent; border: none; }"
            f"QPushButton:hover {{ background-color: {styles.COLOR_SURFACE_HI};"
            " border-radius: 6px; }"
            + styles.tooltip()
        )
        self._show_copy_idle(copy)
        copy.clicked.connect(lambda _checked=False: self._copy(command, copy))
        row.addWidget(copy)
        return field

    @staticmethod
    def _show_copy_idle(button: QPushButton) -> None:
        button.setIcon(qtawesome.icon(_COPY_ICON, color=styles.COLOR_ACCENT))
        button.setProperty("copied", False)

    def _copy(self, command: str, button: QPushButton) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(command)
        button.setIcon(qtawesome.icon(_COPIED_ICON, color=styles.COLOR_RUNNING))
        button.setProperty("copied", True)
        _later(_COPIED_FEEDBACK_MS, button, lambda: self._show_copy_idle(button))

    def _fit_steps_height(self) -> None:
        """A maximum rather than a fixed height: the card's own cap is what makes
        a long list scroll, and this keeps a short one from stretching.

        The minimum hint, not the plain one: a word-wrapped QLabel's sizeHint is
        a guess at a pleasing shape, while every label here has already been told
        the height its text needs."""
        self._steps_area.setMaximumHeight(
            self._steps_container.minimumSizeHint().height())

    def _render_buttons(self, index: int) -> None:
        for i, button in enumerate(self._buttons):
            role = "primary" if i == index else "secondary"
            styles.style_dialog_button(button, role=role, focused=i == index)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _remedy(self, remedy: Remedy) -> None:
        self._on_remedy(remedy)
        self._run_checks()

    def _run_checks(self) -> None:
        report = self._on_recheck()
        if self._resolved(report):
            return
        if self._probe is None or report.subject.verification is None:
            self._apply(report)
            return
        self._confirmation = _Confirmation.RUNNING
        self._check_button.setEnabled(False)
        self._apply(report)
        self._probe.verify(self._verified)

    def _resolved(self, report: ReadinessReport) -> bool:
        """A blocking requirement that has just been met has nothing left to show
        — the card was only ever in the way of starting up."""
        if report.state is Readiness.READY and report.subject.blocking:
            self._finish()
            return True
        return False

    def _verified(self, works: bool) -> None:
        if self._closed:
            return
        self._confirmation = (
            _Confirmation.CONFIRMED if works else _Confirmation.FAILED)
        self._render_confirmation()
        self._check_button.setEnabled(True)

    def _activate(self, index: int) -> None:
        if index == len(self._actions) - 1:
            self._leave()
        elif self._buttons[index].isEnabled():
            self._actions[index]()

    def _leave(self) -> None:
        if self._report.subject.blocking:
            self._close_with(self._on_abort)
        else:
            self._finish()

    def _finish(self) -> None:
        self._close_with(self._on_done)

    def _close_with(self, action: Callable[[], None]) -> None:
        if self._dismiss(sound=Cue.SELECT):
            self._drop_check()
            action()

    def cancel(self) -> None:
        self._drop_check()
        super().cancel()

    def _drop_check(self) -> None:
        if self._probe is not None:
            self._probe.cancel()

    # ── Navigation ───────────────────────────────────────────────────────────

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
            self._leave()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._cursor.handle_pad(Event.UP)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._cursor.handle_pad(Event.DOWN)


def _visible_before_measuring(widget: QWidget) -> None:
    """A child added to a parent that is already on screen stays hidden until the
    next cycle, and a hidden child contributes nothing to its layout's size hint —
    which the callers here read straight away."""
    widget.show()


def _later(delay_ms: int, owner: QWidget, action: Callable[[], None]) -> None:
    """A timer owned by *owner*, so rebuilding the card destroys it rather than
    leaving it to fire at a widget Qt has already deleted."""
    timer = QTimer(owner)
    timer.setSingleShot(True)
    timer.timeout.connect(action)
    timer.start(delay_ms)


def _wrapped(style: str, text: str = "") -> QLabel:
    """*style* comes first because it decides the font the text is measured in.

    Top alignment because the measurement below is deliberately conservative: a
    label given a line more than it turned out to need would otherwise centre its
    text in the surplus and open a gap above it."""
    label = QLabel()
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    label.setStyleSheet(style)
    _set_text(label, text)
    return label


def _set_text(label: QLabel, text: str) -> None:
    """A word-wrapped QLabel gets no height-for-width from the layout it sits in,
    so a paragraph is laid out one line tall and painted clipped. The card is a
    fixed width, so the height its text needs can simply be asked for — after
    polishing, or the measurement is taken in the default font rather than the
    smaller one the stylesheet is about to apply."""
    label.setText(text)
    label.ensurePolished()
    label.setMinimumHeight(label.heightForWidth(_NARROWEST_TEXT_WIDTH) if text else 0)


def _clear(layout: QVBoxLayout) -> None:
    """Unparent before deleting: deleteLater only runs once the event loop comes
    round, and until it does the widget would still be a visible child sitting at
    its old geometry."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class QtSetupView(SetupView):
    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback
        self._current: _SetupDialog | None = None

    def present(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        on_abort: Callable[[], None],
        on_remedy: Callable[[Remedy], None],
        probe: VerificationProbe | None = None,
    ) -> None:
        dialog = _SetupDialog(
            report, on_recheck, on_done, on_abort, on_remedy, probe,
            self._gamepad, self._feedback,
        )
        dialog.destroyed.connect(self._forget)
        self._current = dialog

    @property
    def current(self) -> _SetupDialog | None:
        """The card on screen — None once it closes, so a host that registers it
        in its own overlay group never gets a dead one."""
        return self._current

    def _forget(self) -> None:
        self._current = None
