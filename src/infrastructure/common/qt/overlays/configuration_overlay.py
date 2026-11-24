"""Centred modal with Kasual Desktop's settings."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from domain.audio.kasual_output import OutputPicker, output_choices
from domain.display.choices import screen_choices
from domain.display.selection import DisplaySelection
from domain.input.pad_control import PadControl
from domain.menu.cursor import MenuCursor
from domain.shared.choice import Choice
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.shared.text import truncate
from domain.system.actions import ACTIONS, CONFIGURATION
from domain.system.autostart import Autostart, autostart_label
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.nav_key_map import nav_key_map
from infrastructure.common.qt.ui.toggle_switch import ToggleSwitch
from .base_overlay import BaseOverlay

_CARD_WIDTH       = 640
_LIST_MAX_HEIGHT  = 620
_MAX_LABEL_CHARS  = 44
_MARK_SIZE        = 18
_MARK_GLYPH = "fa5s.check"

_ROW_NORMAL = (
    f"#choicerow {{ background-color: {styles.COLOR_CARD_BG}; border-radius: 8px;"
    " border: 2px solid transparent; }"
)
_ROW_SELECTED = (
    f"#choicerow {{ background-color: {styles.COLOR_BTN_BG}; border-radius: 8px;"
    f" border: 2px solid {styles.COLOR_ACCENT}; }}"
)
_LABEL_PICKABLE   = "font-size: 18px; color: white; background: transparent;"
_LABEL_UNPICKABLE = "font-size: 18px; color: #6b717c; background: transparent;"


@dataclass(frozen=True)
class _Row:
    frame: QFrame
    activate: Callable[[], None]
    pickable: bool = True
    chosen: bool = False


class ConfigurationOverlay(BaseOverlay):
    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        displays: DisplaySelection,
        audio_output: OutputPicker,
        feedback: Feedback,
        autostart: Autostart | None = None,
        parent: QWidget | None = None,
        dim: bool = True,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent, dim=dim)
        self._rows: list[_Row] = []
        self._cursor = MenuCursor(
            count=lambda: len(self._rows),
            render=self._render_selection,
            on_activate=self._activate,
            on_dismiss=self._close,
            feedback=feedback,
            is_selectable=lambda index: self._rows[index].pickable,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(_CARD_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)
        layout.addLayout(self._title_row())

        sections = QWidget()
        sections.setStyleSheet("background: transparent;")
        self._sections = QVBoxLayout(sections)
        self._sections.setContentsMargins(0, 0, 0, 0)
        self._sections.setSpacing(8)
        self._add_section(translate("Kasual Desktop", "Screen"),
                          screen_choices(displays), displays.choose)
        if audio_output.options():
            self._separate_sections()
            self._add_section(translate("Kasual Desktop", "Audio output"),
                              output_choices(audio_output), audio_output.choose)
        if autostart is not None:
            self._separate_sections()
            self._add_startup_section(autostart)
        layout.addWidget(self._scrolling(sections))

        outer.addWidget(card)

        self._cursor.reset(self._initially_selected())
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    def _title_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon(ACTIONS[CONFIGURATION].icon, color="white").pixmap(28, 28))
        icon.setStyleSheet("background: transparent;")
        title = QLabel(translate("Kasual Desktop", "Configuration"))
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        row.addWidget(icon)
        row.addWidget(title)
        row.addStretch()
        return row

    def _scrolling(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(styles.flat_scrollbar())
        content.ensurePolished()
        scroll.setFixedHeight(min(content.sizeHint().height(), _LIST_MAX_HEIGHT))
        self._scroll = scroll
        return scroll

    def _add_section(self, title: str, choices: list[Choice], pick: Callable) -> None:
        self._sections.addWidget(self._section_label(title))
        for choice in choices:
            self._add_row(_Row(
                self._choice_frame(choice),
                activate=partial(self._close_and, partial(pick, choice.value)),
                pickable=choice.pickable,
                chosen=choice.chosen,
            ))

    def _add_startup_section(self, autostart: Autostart) -> None:
        switch = ToggleSwitch()
        switch.setFixedSize(switch.size())
        switch.set_on(autostart.is_enabled(), animate=False)
        self._sections.addWidget(self._section_label(translate("Kasual Desktop", "Startup")))
        self._add_row(_Row(
            self._switch_frame(autostart_label(), switch),
            activate=partial(self._flip, autostart, switch),
        ))

    def _separate_sections(self) -> None:
        self._sections.addSpacing(10)
        self._sections.addWidget(styles.separator())
        self._sections.addSpacing(10)

    def _add_row(self, row: _Row) -> None:
        index = len(self._rows)
        if row.pickable:
            row.frame.mousePressEvent = lambda _event: self._activate_by_pointer(index)
        self._sections.addWidget(row.frame)
        self._rows.append(row)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; color: #9aa0aa; background: transparent;")
        return label

    @staticmethod
    def _row_frame() -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame()
        frame.setObjectName("choicerow")
        frame.setStyleSheet(_ROW_NORMAL)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        return frame, layout

    def _switch_frame(self, text: str, switch: ToggleSwitch) -> QFrame:
        frame, layout = self._row_frame()
        label = QLabel(text)
        label.setStyleSheet(_LABEL_PICKABLE)
        layout.addWidget(label, 1)
        layout.addWidget(switch)
        return frame

    def _choice_frame(self, choice: Choice) -> QFrame:
        frame, layout = self._row_frame()
        mark = QLabel()
        mark.setFixedSize(_MARK_SIZE, _MARK_SIZE)
        mark.setStyleSheet("background: transparent;")
        if choice.chosen:
            mark.setPixmap(
                qta.icon(_MARK_GLYPH, color=styles.COLOR_ACCENT).pixmap(_MARK_SIZE, _MARK_SIZE))
        layout.addWidget(mark)
        label = QLabel(truncate(choice.label, _MAX_LABEL_CHARS))
        label.setStyleSheet(_LABEL_PICKABLE if choice.pickable else _LABEL_UNPICKABLE)
        layout.addWidget(label, 1)
        return frame

    def _initially_selected(self) -> int:
        return next(
            (index for index, row in enumerate(self._rows)
             if row.chosen and row.pickable),
            0,
        )

    def _render_selection(self, index: int) -> None:
        for i, row in enumerate(self._rows):
            row.frame.setStyleSheet(_ROW_SELECTED if i == index else _ROW_NORMAL)
        if 0 <= index < len(self._rows):
            self._scroll.ensureWidgetVisible(self._rows[index].frame)

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    _KEY_MAP = nav_key_map()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._cursor.handle_pad(mapped)

    def _on_outside_click(self) -> None:
        self._close()

    def _activate_by_pointer(self, index: int) -> None:
        self._cursor.hover(index)
        self._activate(index)

    def _activate(self, index: int) -> None:
        self._rows[index].activate()

    def _close_and(self, pick: Callable[[], None]) -> None:
        if self._dismiss(sound=Cue.SELECT):
            self.closed.emit()
            pick()

    def _flip(self, autostart: Autostart, switch: ToggleSwitch) -> None:
        autostart.set_enabled(not autostart.is_enabled())
        switch.set_on(autostart.is_enabled())
        self._feedback.play(Cue.SELECT)

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self.closed.emit()
