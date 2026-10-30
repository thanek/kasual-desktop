"""Centred modal with Kasual Desktop's settings — for now the screen it runs on.

Picking a screen goes through the same `DisplaySelection.choose` the tray menu
uses, so both paths have identical consequences.
"""

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from domain.display.choices import ScreenChoice, screen_choices
from domain.display.selection import DisplaySelection
from domain.input.pad_control import PadControl
from domain.menu.cursor import MenuCursor
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.system.actions import ACTIONS, CONFIGURATION
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.nav_key_map import nav_key_map
from .base_overlay import BaseOverlay

_CARD_WIDTH = 560
_MARK_SIZE  = 18
_MARK_GLYPH = "fa5s.check"

_ROW_NORMAL = (
    f"#screenrow {{ background-color: {styles.COLOR_CARD_BG}; border-radius: 8px;"
    " border: 2px solid transparent; }"
)
_ROW_SELECTED = (
    f"#screenrow {{ background-color: {styles.COLOR_BTN_BG}; border-radius: 8px;"
    f" border: 2px solid {styles.COLOR_ACCENT}; }}"
)
_LABEL_PICKABLE   = "font-size: 18px; color: white; background: transparent;"
_LABEL_UNPICKABLE = "font-size: 18px; color: #6b717c; background: transparent;"


class ConfigurationOverlay(BaseOverlay):
    closed = pyqtSignal()

    def __init__(
        self,
        gamepad: PadControl,
        displays: DisplaySelection,
        feedback: Feedback,
        parent: QWidget | None = None,
        dim: bool = True,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent, dim=dim)
        self._displays = displays
        self._choices = screen_choices(displays)
        self._rows: list[QFrame] = []
        self._cursor = MenuCursor(
            count=lambda: len(self._rows),
            render=self._render_selection,
            on_activate=self._pick,
            on_dismiss=self._close,
            feedback=feedback,
            is_selectable=lambda index: self._choices[index].pickable,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(_CARD_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)
        layout.addLayout(self._title_row())
        layout.addWidget(self._option_label(translate("Kasual Desktop", "Screen")))
        for index, choice in enumerate(self._choices):
            row = self._choice_row(index, choice)
            layout.addWidget(row)
            self._rows.append(row)

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

    @staticmethod
    def _option_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; color: #9aa0aa; background: transparent;")
        return label

    def _choice_row(self, index: int, choice: ScreenChoice) -> QFrame:
        row = QFrame()
        row.setObjectName("screenrow")
        row.setStyleSheet(_ROW_NORMAL)
        if choice.pickable:
            row.mousePressEvent = lambda _event: self._pick_by_pointer(index)

        h = QHBoxLayout(row)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(12)
        mark = QLabel()
        mark.setFixedSize(_MARK_SIZE, _MARK_SIZE)
        mark.setStyleSheet("background: transparent;")
        if choice.chosen:
            mark.setPixmap(
                qta.icon(_MARK_GLYPH, color=styles.COLOR_ACCENT).pixmap(_MARK_SIZE, _MARK_SIZE))
        h.addWidget(mark)
        label = QLabel(choice.label)
        label.setStyleSheet(_LABEL_PICKABLE if choice.pickable else _LABEL_UNPICKABLE)
        h.addWidget(label, 1)
        return row

    def _initially_selected(self) -> int:
        return next(
            (index for index, choice in enumerate(self._choices)
             if choice.chosen and choice.pickable),
            0,
        )

    def _render_selection(self, index: int) -> None:
        for i, row in enumerate(self._rows):
            row.setStyleSheet(_ROW_SELECTED if i == index else _ROW_NORMAL)

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    _KEY_MAP = nav_key_map()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._cursor.handle_pad(mapped)

    def _on_outside_click(self) -> None:
        self._close()

    def _pick_by_pointer(self, index: int) -> None:
        self._cursor.hover(index)
        self._pick(index)

    def _pick(self, index: int) -> None:
        if self._dismiss(sound=Cue.SELECT):
            self.closed.emit()
            self._displays.choose(self._choices[index].display_id)

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self.closed.emit()
