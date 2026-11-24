"""Fullscreen overlay for editing a tile's per-tile settings."""

from collections.abc import Callable, Sequence
from enum import IntEnum

import qtawesome as qta
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event, Trigger
from domain.menu.grid_cursor import GridCursor
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.shared.text import truncate
from infrastructure.common.qt.ui import styles
from .base_overlay import BaseOverlay

_SWATCH_PX = 88
_SWATCH_RADIUS_PX = 16
_SWATCH_GAP_PX = 16
_MAX_SWATCHES_PER_ROW = 10
_RECALL_BUTTON_WIDTH_PX = 400
_CARD_SIDE_ROOM_PX = 160
_MAX_TITLE_CHARS = 40

_RECALL_OPTIONS: tuple[tuple[str, str], ...] = (
    (translate("Desktop", "Pressing"), Trigger.CLICK),
    (translate("Desktop", "Holding"),  Trigger.HOLD_1S),
)

_HINT_BAR_HOME_GLYPH = "fa5s.home"
_GLYPH_DISC_PX = 40
_GLYPH_INNER_PX = 22
_GAP_BETWEEN_LABEL_AND_GLYPH_PX = 14

_KEY_EVENTS = {
    Qt.Key.Key_Return:       Event.SELECT,
    Qt.Key.Key_Enter:        Event.SELECT,
    Qt.Key.Key_Escape:       Event.CANCEL,
    Qt.Key.Key_Left:         Event.LEFT,
    Qt.Key.Key_Right:        Event.RIGHT,
    Qt.Key.Key_Up:           Event.UP,
    Qt.Key.Key_Down:         Event.DOWN,
    Qt.Key.Key_BracketLeft:  Event.SECTION_PREV,
    Qt.Key.Key_BracketRight: Event.SECTION_NEXT,
}


class _Group(IntEnum):
    RECALL = 0
    COLOR = 1
    CLOSE = 2


def _home_glyph_on_dark_disc() -> QIcon:
    canvas = QPixmap(_GAP_BETWEEN_LABEL_AND_GLYPH_PX + _GLYPH_DISC_PX, _GLYPH_DISC_PX)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(styles.COLOR_SURFACE_HI))
    painter.drawEllipse(
        _GAP_BETWEEN_LABEL_AND_GLYPH_PX, 0, _GLYPH_DISC_PX, _GLYPH_DISC_PX)
    house = qta.icon(_HINT_BAR_HOME_GLYPH, color="white").pixmap(
        QSize(_GLYPH_INNER_PX, _GLYPH_INNER_PX))
    inset = (_GLYPH_DISC_PX - _GLYPH_INNER_PX) // 2
    painter.drawPixmap(_GAP_BETWEEN_LABEL_AND_GLYPH_PX + inset, inset, house)
    painter.end()
    return QIcon(canvas)


def _put_icon_after_label(btn: QPushButton, icon: QIcon) -> None:
    btn.setIcon(icon)
    btn.setIconSize(
        QSize(_GAP_BETWEEN_LABEL_AND_GLYPH_PX + _GLYPH_DISC_PX, _GLYPH_DISC_PX))
    btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 18px; color: #d8dee9; background: transparent;")
    return label


def _bind_hover(btn: QPushButton, on_enter: Callable[[], None]) -> None:
    def _enter(event) -> None:
        QPushButton.enterEvent(btn, event)
        on_enter()
    btn.enterEvent = _enter


class TileSettings(BaseOverlay):
    def __init__(
        self,
        app_name: str,
        colors: Sequence[str],
        color: str | None,
        trigger: str,
        on_color_changed: Callable[[str], None],
        on_trigger_changed: Callable[[str], None],
        on_closed: Callable[[], None],
        gamepad: PadControl,
        feedback: Feedback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent)
        self._colors = list(colors)
        self._color = color
        self._trigger = trigger
        self._on_color_changed = on_color_changed
        self._on_trigger_changed = on_trigger_changed
        self._on_closed = on_closed

        self._active_group = _Group.RECALL
        self._recall_index = self._index_of_current_trigger()
        self._color_cursor = GridCursor(
            count=lambda: len(self._colors),
            columns=_MAX_SWATCHES_PER_ROW,
            render=self._refresh_swatches,
            on_activate=self._choose_color,
            on_dismiss=self._close,
            feedback=feedback,
        )

        self._build(app_name)
        self._color_cursor.reset(
            self._colors.index(color) if color in self._colors else 0)
        self._render_all()
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    @property
    def focused_section(self) -> str:
        return self._active_group.name.lower()

    @property
    def colors(self) -> tuple[str, ...]:
        return tuple(self._colors)

    @property
    def columns(self) -> int:
        return _MAX_SWATCHES_PER_ROW

    @property
    def color_under_cursor(self) -> str:
        return self._colors[self._color_cursor.index]

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self, app_name: str) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = self.build_card(self._card_width())
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(20)

        layout.addWidget(self._build_title(app_name))
        layout.addWidget(_section_label(translate("Desktop", "Call Kasual Desktop menu:")))
        layout.addLayout(self._build_recall_row())
        layout.addWidget(styles.separator())
        layout.addWidget(_section_label(translate("Desktop", "Tile color:")))
        layout.addLayout(self._build_swatch_grid())
        layout.addSpacing(8)
        layout.addWidget(self._build_close_button(), 0, Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(card)

    def _card_width(self) -> int:
        per_row = min(len(self._colors), _MAX_SWATCHES_PER_ROW)
        swatches = per_row * (_SWATCH_PX + _SWATCH_GAP_PX)
        recall = len(_RECALL_OPTIONS) * _RECALL_BUTTON_WIDTH_PX + _SWATCH_GAP_PX
        return _CARD_SIDE_ROOM_PX + max(swatches, recall)

    def _build_title(self, app_name: str) -> QLabel:
        title = QLabel(translate("Desktop", "Settings — {0}")
                       .format(truncate(app_name, _MAX_TITLE_CHARS)))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        return title

    def _build_recall_row(self) -> QLayout:
        row = QHBoxLayout()
        row.setSpacing(_SWATCH_GAP_PX)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        home_icon = _home_glyph_on_dark_disc()
        self._recall_buttons: list[QPushButton] = []
        for i, (label, _trigger) in enumerate(_RECALL_OPTIONS):
            btn = QPushButton(translate("Desktop", label))
            _put_icon_after_label(btn, home_icon)
            btn.setFixedSize(_RECALL_BUTTON_WIDTH_PX, _SWATCH_PX)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(
                lambda _checked=False, idx=i: self._choose_recall(idx))
            _bind_hover(btn, lambda idx=i: self._focus_recall(idx))
            row.addWidget(btn)
            self._recall_buttons.append(btn)
        return row

    def _build_swatch_grid(self) -> QLayout:
        grid = QGridLayout()
        grid.setSpacing(_SWATCH_GAP_PX)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._swatches: list[QPushButton] = []
        for i in range(len(self._colors)):
            btn = QPushButton()
            btn.setFixedSize(_SWATCH_PX, _SWATCH_PX)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(
                lambda _checked=False, idx=i: self._choose_color(idx))
            _bind_hover(btn, lambda idx=i: self._focus_color(idx))
            grid.addWidget(btn, i // _MAX_SWATCHES_PER_ROW, i % _MAX_SWATCHES_PER_ROW)
            self._swatches.append(btn)
        return grid

    def _build_close_button(self) -> QPushButton:
        self._btn_close = QPushButton("✘  " + translate("Desktop", "Close"))
        self._btn_close.setMinimumSize(210, 80)
        self._btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_close.clicked.connect(self._close)
        _bind_hover(self._btn_close, self._focus_close)
        return self._btn_close

    # ── Gamepad ──────────────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.CANCEL:
            self._close()
        elif event == Event.SECTION_PREV:
            self._switch_group(-1)
        elif event == Event.SECTION_NEXT:
            self._switch_group(+1)
        elif event == Event.SELECT:
            self._activate()
        elif self._active_group == _Group.RECALL:
            self._recall_nav(event)
        elif self._active_group == _Group.COLOR:
            self._color_nav(event)
        elif event == Event.UP:
            self._switch_group(-1)

    def _recall_nav(self, event: str) -> None:
        if event == Event.LEFT:
            self._choose_recall((self._recall_index - 1) % len(_RECALL_OPTIONS))
        elif event == Event.RIGHT:
            self._choose_recall((self._recall_index + 1) % len(_RECALL_OPTIONS))
        elif event == Event.DOWN:
            self._switch_group(+1)

    def _color_nav(self, event: str) -> None:
        row = self._color_cursor.index // _MAX_SWATCHES_PER_ROW
        last_row = (len(self._colors) - 1) // _MAX_SWATCHES_PER_ROW
        if event == Event.UP and row == 0:
            self._switch_group(-1)
        elif event == Event.DOWN and row == last_row:
            self._switch_group(+1)
        else:
            self._color_cursor.handle_pad(event)

    # ── Keyboard / mouse ─────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = _KEY_EVENTS.get(event.key())
        if mapped is not None:
            self._handle_pad(mapped)

    # ── Focus groups ─────────────────────────────────────────────────────────

    def _switch_group(self, delta: int) -> None:
        new = max(_Group.RECALL, min(self._active_group + delta, _Group.CLOSE))
        if new == self._active_group:
            return
        if new == _Group.RECALL:
            self._recall_index = self._index_of_current_trigger()
        self._active_group = _Group(new)
        self._render_all()
        self._feedback.play(Cue.CURSOR)

    def _activate(self) -> None:
        if self._active_group == _Group.RECALL:
            self._choose_recall(self._recall_index)
        elif self._active_group == _Group.COLOR:
            self._choose_color(self._color_cursor.index)
        else:
            self._close()

    def _focus_recall(self, index: int) -> None:
        self._move_focus(_Group.RECALL, changed=self._recall_index != index)
        self._recall_index = index
        self._render_all()

    def _focus_color(self, index: int) -> None:
        self._move_focus(_Group.COLOR, changed=self._color_cursor.index != index)
        self._color_cursor.index = index
        self._render_all()

    def _focus_close(self) -> None:
        self._move_focus(_Group.CLOSE, changed=False)
        self._render_all()

    def _move_focus(self, group: _Group, *, changed: bool) -> None:
        if self._active_group != group or changed:
            self._feedback.play(Cue.CURSOR)
        self._active_group = group

    # ── Choosing / closing ───────────────────────────────────────────────────

    def _index_of_current_trigger(self) -> int:
        return [trigger for _label, trigger in _RECALL_OPTIONS].index(self._trigger)

    def _choose_recall(self, index: int) -> None:
        self._recall_index = index
        _label, trigger = _RECALL_OPTIONS[index]
        if trigger == self._trigger:
            self._render_recall()
            return
        self._trigger = trigger
        self._render_recall()
        self._on_trigger_changed(trigger)
        self._feedback.play(Cue.CURSOR)

    def _choose_color(self, index: int) -> None:
        color = self._colors[index]
        if color == self._color:
            return
        self._color = color
        self._refresh_swatches(self._color_cursor.index)
        self._on_color_changed(color)
        self._feedback.play(Cue.CURSOR)

    def _close(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._on_closed()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render_all(self) -> None:
        self._render_recall()
        self._refresh_swatches(self._color_cursor.index)
        self._render_close()

    def _render_recall(self) -> None:
        group_focused = self._active_group == _Group.RECALL
        for i, btn in enumerate(self._recall_buttons):
            _label, trigger = _RECALL_OPTIONS[i]
            styles.style_dialog_button(
                btn,
                role="selected" if trigger == self._trigger else "secondary",
                focused=group_focused and i == self._recall_index)

    def _render_close(self) -> None:
        styles.style_dialog_button(
            self._btn_close, role="primary",
            focused=self._active_group == _Group.CLOSE)

    def _refresh_swatches(self, index: int) -> None:
        group_focused = self._active_group == _Group.COLOR
        for i, (btn, color) in enumerate(zip(self._swatches, self._colors)):
            if group_focused and i == index:
                border_color = "white"
            elif color == self._color:
                border_color = styles.COLOR_ACCENT
            else:
                border_color = "#888888"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color};"
                f" border: 3px solid {border_color};"
                f" border-radius: {_SWATCH_RADIUS_PX}px; }}"
            )
