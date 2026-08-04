"""Qt DrmSetupView: the Widevine readiness checklist shown during provisioning.

Commands are offered for copying, never run: the vendor installer asks for root
and for the user's acceptance of Google's licence.
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

from domain.drm.plan import Readiness, ReadinessReport, StepStatus
from domain.drm.ports import DrmSetupView, PlaybackProbe
from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Keyboard
from .base_overlay import BaseOverlay

_CARD_WIDTH = 960
_CARD_MARGIN = 40
# Translations run considerably longer than the English source they are sized by.
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
_STEP_INDENT_PX = 28


class _Verification(enum.Enum):
    UNKNOWN = "unknown"
    RUNNING = "running"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class _DrmSetupDialog(BaseOverlay):
    """Leaving starts the session, so only Continue — kept last — and Escape do
    it; the backdrop keeps BaseOverlay's do-nothing click."""

    def __init__(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        probe: PlaybackProbe | None,
        gamepad: PadControl,
        feedback: Feedback,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback,
                         keyboard=Keyboard.ON_DEMAND)
        self._report = report
        self._on_recheck = on_recheck
        self._on_done = on_done
        self._probe = probe
        self._verification = _Verification.UNKNOWN
        self._buttons: list[QPushButton] = []
        self._actions: list[Callable[[], None]] = []

        self._cursor = MenuCursor(
            count=lambda: len(self._actions),
            render=self._render_buttons,
            on_activate=self._activate,
            on_dismiss=self._finish,
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

        layout.addWidget(self._build_title())
        self._status_module = self._build_status_label()
        layout.addWidget(self._status_module)
        self._module_detail = self._build_detail_label()
        layout.addWidget(self._module_detail)
        self._notice = self._build_detail_label(muted=True)
        layout.addWidget(self._notice)
        layout.addWidget(self._build_steps_area())
        self._status_playback = self._build_status_label()
        layout.addWidget(self._status_playback)
        self._playback_detail = self._build_detail_label()
        layout.addWidget(self._playback_detail)
        layout.addLayout(self._build_buttons())
        outer.addWidget(card)

        self._apply(report)
        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Building ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_title() -> QLabel:
        label = QLabel(translate("Kasual Desktop", "Streaming apps need Widevine"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"font-size: 28px; color: {styles.COLOR_ACCENT}; font-weight: bold;"
            " background: transparent;"
        )
        return label

    @staticmethod
    def _build_status_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        return label

    @staticmethod
    def _build_detail_label(*, muted: bool = False) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        color = styles.COLOR_TRACK if muted else styles.COLOR_TEXT
        label.setStyleSheet(
            f"font-size: 16px; color: {color}; background: transparent;"
            f" padding-left: {_STEP_INDENT_PX}px;")
        return label

    def _build_steps_area(self) -> QScrollArea:
        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background: transparent;")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(14)

        self._steps_area = QScrollArea()
        self._steps_area.setWidget(self._steps_container)
        self._steps_area.setWidgetResizable(True)
        self._steps_area.setFrameShape(QFrame.Shape.NoFrame)
        self._steps_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._steps_area.viewport().setStyleSheet("background: transparent;")
        self._steps_area.setStyleSheet(styles.flat_scrollbar())
        return self._steps_area

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        self._check_button = self._add_button(
            row, translate("Kasual Desktop", "Check again"), self._run_checks)
        self._add_button(row, translate("Kasual Desktop", "Continue"), self._finish)
        return row

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
        label.setText(f"{_DONE_MARK}  {text}" if met else f"{_PENDING_MARK}  {text}")
        color = styles.COLOR_RUNNING if met else styles.COLOR_TEXT
        weight = "bold" if met else "normal"
        label.setStyleSheet(
            f"font-size: 20px; color: {color}; font-weight: {weight};"
            " background: transparent;")

    def _apply(self, report: ReadinessReport) -> None:
        self._report = report
        self._render_module(report)
        self._render_playback()
        self._render_buttons(self._cursor.index)

    def _render_module(self, report: ReadinessReport) -> None:
        installed = report.state is Readiness.READY
        self._set_status(
            self._status_module,
            translate("Kasual Desktop", "Widevine is installed") if installed
            else translate("Kasual Desktop", "Widevine is not installed"),
            met=installed,
        )
        detail = "" if installed else self._module_guidance(report)
        self._module_detail.setText(detail)
        self._module_detail.setVisible(bool(detail))
        self._notice.setText("" if installed else report.notice)
        self._notice.setVisible(not installed and bool(report.notice))
        self._rebuild_steps(() if installed else report.steps)

    @staticmethod
    def _module_guidance(report: ReadinessReport) -> str:
        if report.state is Readiness.UNSUPPORTED:
            return translate(
                "Kasual Desktop",
                "Kasual Desktop has no Widevine recipe for this system. The apps "
                "stay installed in case you set it up yourself.",
            )
        return translate(
            "Kasual Desktop",
            "Work through these steps in a terminal, then check again. You can "
            "also continue now and come back later.",
        )

    def _render_playback(self) -> None:
        if self._probe is None:
            self._status_playback.setVisible(False)
            self._playback_detail.setVisible(False)
            return
        text, detail = self._playback_text()
        self._set_status(self._status_playback, text,
                         met=self._verification is _Verification.CONFIRMED)
        self._playback_detail.setText(detail)
        self._playback_detail.setVisible(bool(detail))

    def _playback_text(self) -> tuple[str, str]:
        if self._verification is _Verification.CONFIRMED:
            return translate(
                "Kasual Desktop", "Protected video plays on this system"), ""
        if self._verification is _Verification.RUNNING:
            return translate("Kasual Desktop", "Checking playback…"), ""
        if self._verification is _Verification.FAILED:
            return (
                translate("Kasual Desktop", "Protected video does not play yet"),
                translate(
                    "Kasual Desktop",
                    "The module is installed but did not load. It may have been "
                    "built for a different system — a kernel with a different "
                    "memory page size is the usual reason. Reinstall it and "
                    "check again.",
                )
                if self._report.state is Readiness.READY else
                translate(
                    "Kasual Desktop",
                    "There is nothing to play protected video with until Widevine "
                    "is installed.",
                ),
            )
        return (
            translate("Kasual Desktop", "Playback has not been checked yet"),
            translate(
                "Kasual Desktop",
                "Checking starts a short test playback with the installed module.",
            ),
        )

    def _rebuild_steps(self, steps: tuple[StepStatus, ...]) -> None:
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for number, status in enumerate(steps, start=1):
            step = self._step_widget(number, status)
            self._steps_layout.addWidget(step)
            # A child added to an already-visible parent stays hidden until the
            # next cycle, and a hidden child contributes nothing to the layout's
            # size hint — which _fit_steps_height reads straight away.
            step.show()
        self._steps_area.setVisible(bool(steps))
        if steps:
            self._fit_steps_height()

    def _step_widget(self, number: int, status: StepStatus) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(_STEP_INDENT_PX, 0, 0, 0)
        layout.setSpacing(4)

        mark = _DONE_MARK if status.done else _PENDING_MARK
        color = styles.COLOR_RUNNING if status.done else styles.COLOR_ACCENT
        heading = QLabel(f"{mark}  {number}. {status.step.title}")
        heading.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {color};"
            " background: transparent;")
        layout.addWidget(heading)

        instruction = QLabel(status.step.instruction)
        instruction.setWordWrap(True)
        instruction.setStyleSheet(
            f"font-size: 16px; color: {styles.COLOR_TEXT}; background: transparent;")
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

        label = QLabel(command)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setCursor(Qt.CursorShape.IBeamCursor)
        label.setStyleSheet(
            f"font-family: monospace; font-size: 16px; color: {styles.COLOR_ACCENT};"
            " background: transparent;")
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
        QTimer.singleShot(_COPIED_FEEDBACK_MS, lambda: self._show_copy_idle(button))

    def _fit_steps_height(self) -> None:
        """A maximum rather than a fixed height: the card's own cap is what makes
        a long list scroll, and this keeps a short one from stretching."""
        self._steps_area.setMaximumHeight(self._steps_container.sizeHint().height())

    def _render_buttons(self, index: int) -> None:
        for i, button in enumerate(self._buttons):
            role = "primary" if i == index else "secondary"
            styles.style_dialog_button(button, role=role, focused=i == index)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _run_checks(self) -> None:
        report = self._on_recheck()
        if self._probe is None:
            self._apply(report)
            return
        self._verification = _Verification.RUNNING
        self._check_button.setEnabled(False)
        self._apply(report)
        self._probe.verify(self._verified)

    def _verified(self, plays: bool) -> None:
        if self._closed:
            return
        self._verification = (
            _Verification.CONFIRMED if plays else _Verification.FAILED)
        self._render_playback()
        self._check_button.setEnabled(True)

    def _activate(self, index: int) -> None:
        if index == len(self._actions) - 1:
            self._finish()
        elif self._buttons[index].isEnabled():
            self._actions[index]()

    def _finish(self) -> None:
        if self._dismiss(sound=Cue.SELECT):
            # Continue is deliberately live while a check runs.
            self._drop_check()
            self._on_done()

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
            self._finish()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._cursor.handle_pad(Event.UP)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._cursor.handle_pad(Event.DOWN)


class QtDrmSetupView(DrmSetupView):
    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback
        self._current: _DrmSetupDialog | None = None

    def present(
        self,
        report: ReadinessReport,
        on_recheck: Callable[[], ReadinessReport],
        on_done: Callable[[], None],
        probe: PlaybackProbe | None = None,
    ) -> None:
        self._current = _DrmSetupDialog(
            report, on_recheck, on_done, probe, self._gamepad, self._feedback,
        )

    @property
    def current(self) -> _DrmSetupDialog | None:
        """The card on screen, for a host that has to place it in its own
        overlay group."""
        return self._current
