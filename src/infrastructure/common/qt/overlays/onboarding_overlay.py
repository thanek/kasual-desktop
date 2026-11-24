"""First-run app picker, reused by the [＋] tile — the Qt side of provisioning."""

import logging
from collections.abc import Callable
from functools import partial

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QLabel, QSizePolicy,
    QScrollArea, QFrame,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.provisioning.candidate import CandidateApp
from domain.provisioning.ports import ProvisioningView
from domain.provisioning.selection import AppSelection
from domain.shared.feedback import Cue, Feedback
from domain.system.autostart import AutostartChoice, autostart_label
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Keyboard
from infrastructure.common.qt.ui.target_screen import target_screen
from infrastructure.common.qt.ui.toggle_switch import ToggleSwitch
from .base_overlay import BaseOverlay

logger = logging.getLogger(__name__)

_NOTHING_FULLSCREEN_TO_STEAL_FOCUS_FROM = Keyboard.ON_DEMAND
_ROW_ICON_PX     = 36
_CARD_WIDTH      = 640
_ROW_HEIGHT      = 62
_ROW_SPACING     = 8
_APP_FONT_PX     = 24
_SETTING_FONT_PX = 18
_MAX_LIST_SHARE_OF_SCREEN = 0.55
_MAX_LIST_HEIGHT_WITHOUT_SCREEN = 560
_SPACE_AROUND_SEPARATOR = 6
_TOGGLE_MARGIN_CLEARING_SCROLLBAR = 36


class _ToggleRow(QPushButton):
    def __init__(
        self,
        text: str,
        is_on: Callable[[], bool],
        flip: Callable[[], None],
        font_px: int = _APP_FONT_PX,
    ) -> None:
        super().__init__(text)
        self._is_on = is_on
        self._flip = flip
        self._font_px = font_px
        self.toggle = ToggleSwitch(self)
        self.toggle.set_on(is_on(), animate=False)
        self.setMinimumHeight(_ROW_HEIGHT)
        self._let_long_text_clip_instead_of_widening_the_card()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def flip(self) -> None:
        self._flip()
        self.toggle.set_on(self._is_on())

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(
            styles.home_menu_item_selected(self._font_px) if selected
            else styles.home_menu_item_normal(self._font_px))

    def _let_long_text_clip_instead_of_widening_the_card(self) -> None:
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        x = self.width() - self.toggle.width() - _TOGGLE_MARGIN_CLEARING_SCROLLBAR
        y = (self.height() - self.toggle.height()) // 2
        self.toggle.move(x, y)


class OnboardingOverlay(BaseOverlay, ProvisioningView, metaclass=ProtocolQtMeta):
    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        super().__init__(gamepad, self._handle_pad, feedback,
                         keyboard=_NOTHING_FULLSCREEN_TO_STEAL_FOCUS_FROM)
        self._candidates: list[CandidateApp] = []
        self._selection: AppSelection | None = None
        self._on_confirm: Callable[[list[CandidateApp]], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._rows:    list[_ToggleRow] = []
        self._confirm: QPushButton | None = None
        self._row_left_for_confirm: int = 0

        self._cursor = MenuCursor(
            count=lambda: len(self._rows) + 1,
            render=self._render,
            on_activate=self._activate,
            on_dismiss=lambda: None,
            feedback=feedback,
            wrap=False,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(_CARD_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(_ROW_SPACING)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._title = QLabel(self.tr("Welcome — pick your apps"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"font-size: 28px; color: {styles.COLOR_ACCENT}; font-weight: bold;"
            " background: transparent; padding-bottom: 8px;"
        )
        layout.addWidget(self._title)

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(_ROW_SPACING)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._rows_container)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self._scroll.setStyleSheet(styles.flat_scrollbar())
        layout.addWidget(self._scroll)

        self._settings_layout = QVBoxLayout()
        self._settings_layout.setSpacing(_ROW_SPACING)
        layout.addLayout(self._settings_layout)

        self._confirm = QPushButton(self.tr("Confirm"))
        self._confirm.setMinimumHeight(_ROW_HEIGHT)
        self._confirm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._confirm.clicked.connect(self._confirm_clicked)
        layout.addWidget(self._confirm)

        outer.addWidget(card)

    # ── ProvisioningView ─────────────────────────────────────────────────────

    def present(
        self,
        candidates: list[CandidateApp],
        on_confirm: Callable[[list[CandidateApp]], None],
        on_cancel: Callable[[], None] | None = None,
        title: str | None = None,
        autostart: AutostartChoice | None = None,
    ) -> None:
        self._candidates = list(candidates)
        self._selection = AppSelection(self._candidates)
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        if title is not None:
            self._title.setText(title)
        self._build_app_rows()
        if autostart is not None:
            self._build_autostart_row(autostart)
        self._bind_hover(self._confirm, len(self._rows))
        self._fit_scroll_height()
        self._cursor.reset(0)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    def _fit_scroll_height(self) -> None:
        n = max(1, len(self._candidates))
        content = n * _ROW_HEIGHT + (n - 1) * _ROW_SPACING
        screen = target_screen()
        cap = (int(screen.availableGeometry().height() * _MAX_LIST_SHARE_OF_SCREEN)
               if screen else _MAX_LIST_HEIGHT_WITHOUT_SCREEN)
        self._scroll.setFixedHeight(min(content, cap))

    # ── Building ─────────────────────────────────────────────────────────────

    def _build_app_rows(self) -> None:
        assert self._selection is not None
        self._rows.clear()
        for i, candidate in enumerate(self._candidates):
            row = _ToggleRow(
                f"  {self.tr(candidate.app.name)}",
                is_on=partial(self._selection.is_selected, i),
                flip=partial(self._selection.toggle, i),
            )
            icon = self._candidate_icon(candidate)
            if icon is not None:
                row.setIcon(icon)
                row.setIconSize(QSize(_ROW_ICON_PX, _ROW_ICON_PX))
            self._add_row(row, self._rows_layout)

    def _build_autostart_row(self, autostart: AutostartChoice) -> None:
        self._settings_layout.addSpacing(_SPACE_AROUND_SEPARATOR)
        self._settings_layout.addWidget(styles.separator())
        self._settings_layout.addSpacing(_SPACE_AROUND_SEPARATOR)
        row = _ToggleRow(
            autostart_label(),
            is_on=lambda: autostart.is_on,
            flip=autostart.toggle,
            font_px=_SETTING_FONT_PX,
        )
        self._add_row(row, self._settings_layout)
        self._settings_layout.addSpacing(_SPACE_AROUND_SEPARATOR)

    def _add_row(self, row: _ToggleRow, layout: QVBoxLayout) -> None:
        index = len(self._rows)
        row.clicked.connect(lambda: self._row_clicked(index))
        self._bind_hover(row, index)
        layout.addWidget(row)
        self._rows.append(row)

    @staticmethod
    def _candidate_icon(candidate: CandidateApp) -> QIcon | None:
        from infrastructure.common.qt.icons import resolve_app_icon
        return resolve_app_icon(candidate.app)

    def _bind_hover(self, btn: QPushButton, index: int) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            self._cursor.hover(index)
        btn.enterEvent = _enter

    # ── Navigation (delegated to the domain cursor) ──────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.CANCEL and self._is_dismissable():
            self._cancel()
            return
        to_confirm = event in (Event.RIGHT, Event.SECTION_NEXT)
        to_list    = event in (Event.LEFT, Event.SECTION_PREV)
        if to_confirm and self._rows and self._cursor.index < len(self._rows):
            self._row_left_for_confirm = self._cursor.index
            self._cursor.hover(len(self._rows))
            return
        if to_list and self._cursor.index == len(self._rows) and self._rows:
            self._cursor.hover(min(self._row_left_for_confirm, len(self._rows) - 1))
            return
        self._cursor.handle_pad(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up:
            self._handle_pad(Event.UP)
        elif key == Qt.Key.Key_Down:
            self._handle_pad(Event.DOWN)
        elif key == Qt.Key.Key_Left:
            self._handle_pad(Event.LEFT)
        elif key == Qt.Key.Key_Right:
            self._handle_pad(Event.RIGHT)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cursor.handle_pad(Event.SELECT)
        elif key == Qt.Key.Key_Escape and self._is_dismissable():
            self._cancel()
        elif key == Qt.Key.Key_Space:
            index = self._cursor.index
            if index < len(self._rows):
                self._toggle(index)

    def _row_clicked(self, index: int) -> None:
        self._cursor.hover(index)
        self._activate(index)

    def _confirm_clicked(self) -> None:
        self._confirm_selection()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _activate(self, index: int) -> None:
        if index < len(self._rows):
            self._toggle(index)
        else:
            self._confirm_selection()

    def _toggle(self, index: int) -> None:
        self._rows[index].flip()
        self._feedback.play(Cue.SELECT)

    def _confirm_selection(self) -> None:
        assert self._selection is not None
        chosen = self._selection.chosen()
        if self._dismiss(sound=Cue.SELECT) and self._on_confirm is not None:
            self._on_confirm(chosen)

    def _cancel(self) -> None:
        if self._dismiss(sound=Cue.EXIT) and self._on_cancel is not None:
            self._on_cancel()

    def _is_dismissable(self) -> bool:
        return self._on_cancel is not None

    def _on_outside_click(self) -> None:
        if self._is_dismissable():
            self._cancel()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self, index: int) -> None:
        for i, row in enumerate(self._rows):
            row.set_selected(i == index)
        if self._confirm is not None:
            on_confirm_row = index == len(self._rows)
            styles.style_dialog_button(
                self._confirm, role="primary", focused=on_confirm_row)
        if index < len(self._candidates):
            self._scroll.ensureWidgetVisible(self._rows[index])


class OnboardingOverlayFactory:
    """Builds the onboarding overlay bound to the gamepad + feedback, so the
    composition root can create the view without knowing its wiring."""

    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback

    def create(self) -> OnboardingOverlay:
        return OnboardingOverlay(self._gamepad, self._feedback)
