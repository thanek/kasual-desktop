"""Fullscreen overlay for editing a tile's per-tile settings.

Shown from the Tile Popover's *Settings* action. Both sections are visible at
once in a single card:

  * Recall trigger — how BTN_MODE recalls the Home menu over this tile's app:
    an immediate click (the default) or a ~1 s hold. Persisted as
    ``X-Kasual-RecallMenuTrigger`` (the default is the sentinel the adapter
    strips from the file).
  * Tile colour — the swatch grid. Persisted as ``X-Kasual-Color``.

Three focus groups (Recall, colour grid, action buttons) cycle with LB/RB or
by spilling past an edge with the D-pad. A stages a pick — the colour previews
live on the tile via *on_color_preview*; Save commits both values; Cancel (or
B / Escape / backdrop / BTN_MODE) reverts the preview.
"""

from collections.abc import Callable, Sequence

import qtawesome as qta
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event, Trigger
from domain.menu.grid_cursor import GridCursor
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.shared.text import truncate
from infrastructure.common.qt.ui import styles
from .base_overlay import BaseOverlay

_SWATCH = 88        # swatch side, px
_SWATCH_RADIUS = 16
_SWATCH_GAP = 16    # spacing between swatches, px
_MAX_PER_ROW = 10   # wrap the palette into rows of at most this many swatches

_RECALL_OPTIONS: tuple[tuple[str, str], ...] = (
    # (label, trigger value) — the first is the default; the order is the
    # left-to-right navigation order in the Recall section.
    (translate("Desktop", "Pressing"),   Trigger.CLICK),
    (translate("Desktop", "Holding"),     Trigger.HOLD_1S),
)

# The same glyph the hint bar shows for BTN_MODE, so both surfaces name one button.
_HOME_GLYPH = "fa5s.home"
_GLYPH_DISC = 40      # disc diameter, px
_GLYPH_INNER = 22     # house glyph within the disc, px
_GLYPH_GAP = 14       # transparent lead-in that keeps the disc off the label, px


def _home_button_icon() -> QIcon:
    """The recall button's BTN_MODE mark: a white house on a dark disc, legible
    whether the button is idle (dark) or focused (light). The disc is inset from
    the pixmap's leading edge so it never crowds the label beside it."""
    canvas = QPixmap(_GLYPH_GAP + _GLYPH_DISC, _GLYPH_DISC)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(styles.COLOR_SURFACE_HI))
    painter.drawEllipse(_GLYPH_GAP, 0, _GLYPH_DISC, _GLYPH_DISC)
    house = qta.icon(_HOME_GLYPH, color="white").pixmap(
        QSize(_GLYPH_INNER, _GLYPH_INNER))
    inset = (_GLYPH_DISC - _GLYPH_INNER) // 2
    painter.drawPixmap(_GLYPH_GAP + inset, inset, house)
    painter.end()
    return QIcon(canvas)

# Focus groups (cycled by LB/RB, clamped at the edges).
_RECALL = 0
_COLOR = 1
_ACTIONS = 2


class TileSettings(BaseOverlay):
    """Two-section settings modal for a tile's colour and recall-menu trigger.

    Both sections are visible at once. *on_color_preview* fires the moment a
    swatch is staged (A), recolouring the tile live so the user sees the change
    before committing. *on_save* persists both the staged colour and the staged
    trigger; *on_cancel* reverts the preview (the host restores the original
    colour) and closes. The modal tracks the original colour so it can hand it
    back on cancel.
    """

    def __init__(
        self,
        app_name: str,
        colors: Sequence[str],
        original_color: str | None,
        original_trigger: str,
        on_color_preview: Callable[[str], None],
        on_save: Callable[[str, str], None],
        on_cancel: Callable[[], None],
        gamepad: PadControl,
        feedback: Feedback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent)
        self._colors = list(colors)
        self._on_color_preview = on_color_preview
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._original_color = original_color
        self._pending_color = original_color
        self._pending_trigger = original_trigger

        self._active_group = _RECALL
        self._recall_index = next(
            i for i, (_, v) in enumerate(_RECALL_OPTIONS) if v == original_trigger
        )
        # Action buttons: 0 = Cancel, 1 = Save. Start on Save so A commits.
        self._action_index = 1

        self._color_cursor = GridCursor(
            count=lambda: len(self._colors),
            columns=_MAX_PER_ROW,
            render=self._refresh_swatches,
            on_activate=self._stage_color,
            on_dismiss=self._cancel,
            feedback=feedback,
        )

        # ── Build the card ───────────────────────────────────────────────────
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        per_row = min(len(self._colors), _MAX_PER_ROW)
        swatch_w = 160 + per_row * (_SWATCH + _SWATCH_GAP)
        recall_w = 160 + 2 * 400 + _SWATCH_GAP
        card = self.build_card(max(swatch_w, recall_w))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(20)

        title = QLabel(translate("Desktop", "Settings — {0}")
                       .format(truncate(app_name, 40)))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        layout.addWidget(title)

        # ── Recall section ───────────────────────────────────────────────────
        recall_label = QLabel(translate("Desktop", "Call Kasual Desktop menu:"))
        recall_label.setStyleSheet(
            "font-size: 18px; color: #d8dee9; background: transparent;")
        layout.addWidget(recall_label)

        recall_row = QHBoxLayout()
        recall_row.setSpacing(_SWATCH_GAP)
        recall_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recall_buttons: list[QPushButton] = []
        home_icon = _home_button_icon()
        for i, (label, _value) in enumerate(_RECALL_OPTIONS):
            btn = QPushButton(translate("Desktop", label))
            btn.setIcon(home_icon)
            btn.setIconSize(QSize(_GLYPH_GAP + _GLYPH_DISC, _GLYPH_DISC))
            # Right-to-left lays the glyph after the verb: "Pressing [home]".
            btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            btn.setFixedSize(400, _SWATCH)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(
                lambda _checked=False, idx=i: self._stage_recall(idx))
            self._bind_hover(btn, lambda idx=i: self._focus_recall(idx))
            recall_row.addWidget(btn)
            self._recall_buttons.append(btn)
        layout.addLayout(recall_row)

        layout.addWidget(styles.separator())

        # ── Colour section ───────────────────────────────────────────────────
        color_label = QLabel(translate("Desktop", "Tile color:"))
        color_label.setStyleSheet(
            "font-size: 18px; color: #d8dee9; background: transparent;")
        layout.addWidget(color_label)

        grid = QGridLayout()
        grid.setSpacing(_SWATCH_GAP)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._swatches: list[QPushButton] = []
        for i, color in enumerate(self._colors):
            btn = QPushButton()
            btn.setFixedSize(_SWATCH, _SWATCH)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(
                lambda _checked=False, idx=i: self._stage_color(idx))
            self._bind_hover(btn, lambda idx=i: self._focus_color(idx))
            grid.addWidget(btn, i // _MAX_PER_ROW, i % _MAX_PER_ROW)
            self._swatches.append(btn)
        layout.addLayout(grid)

        # ── Action buttons ───────────────────────────────────────────────────
        layout.addSpacing(8)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_cancel = QPushButton("✘  " + translate("Desktop", "Cancel"))
        self._btn_save = QPushButton("✔  " + translate("Desktop", "Save"))
        for i, btn in enumerate((self._btn_cancel, self._btn_save)):
            btn.setMinimumSize(210, 80)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._bind_hover(btn, lambda idx=i: self._focus_action(idx))
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_save.clicked.connect(self._save)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_save)
        layout.addLayout(btn_row)

        outer.addWidget(card)

        start = (self._colors.index(original_color)
                 if original_color in self._colors else 0)
        self._color_cursor.reset(start)
        self._render_all()
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Gamepad ──────────────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == Event.CANCEL:
            self._cancel()
            return
        if event == Event.SECTION_PREV:
            self._switch_group(-1)
            return
        if event == Event.SECTION_NEXT:
            self._switch_group(+1)
            return
        if event == Event.SELECT:
            self._activate()
            return
        if self._active_group == _RECALL:
            self._recall_nav(event)
        elif self._active_group == _COLOR:
            self._color_nav(event)
        else:
            self._actions_nav(event)

    def _recall_nav(self, event: str) -> None:
        if event == Event.LEFT:
            self._stage_recall((self._recall_index - 1) % len(_RECALL_OPTIONS))
        elif event == Event.RIGHT:
            self._stage_recall((self._recall_index + 1) % len(_RECALL_OPTIONS))
        elif event == Event.DOWN:
            self._switch_group(+1)
        elif event == Event.UP:
            pass   # first group — clamp silently

    def _color_nav(self, event: str) -> None:
        if event == Event.UP and self._color_cursor.index < _MAX_PER_ROW:
            self._switch_group(-1)
            return
        if event == Event.DOWN:
            n = len(self._colors)
            last_row_start = ((n - 1) // _MAX_PER_ROW) * _MAX_PER_ROW
            if self._color_cursor.index >= last_row_start:
                self._switch_group(+1)
                return
        self._color_cursor.handle_pad(event)

    def _actions_nav(self, event: str) -> None:
        if event == Event.LEFT:
            self._action_index = (self._action_index - 1) % 2
            self._render_actions()
            self._feedback.play(Cue.CURSOR)
        elif event == Event.RIGHT:
            self._action_index = (self._action_index + 1) % 2
            self._render_actions()
            self._feedback.play(Cue.CURSOR)
        elif event == Event.UP:
            self._switch_group(-1)

    # ── Keyboard / mouse ─────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._cancel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_pad(Event.SELECT)
        elif key == Qt.Key.Key_Escape:
            self._handle_pad(Event.CANCEL)
        elif key == Qt.Key.Key_Left:
            self._handle_pad(Event.LEFT)
        elif key == Qt.Key.Key_Right:
            self._handle_pad(Event.RIGHT)
        elif key == Qt.Key.Key_Up:
            self._handle_pad(Event.UP)
        elif key == Qt.Key.Key_Down:
            self._handle_pad(Event.DOWN)
        elif key == Qt.Key.Key_BracketLeft:
            self._handle_pad(Event.SECTION_PREV)
        elif key == Qt.Key.Key_BracketRight:
            self._handle_pad(Event.SECTION_NEXT)

    # ── Focus groups ─────────────────────────────────────────────────────────

    def _switch_group(self, delta: int) -> None:
        new = max(0, min(self._active_group + delta, _ACTIONS))
        if new == self._active_group:
            return
        if new == _RECALL:
            for i, (_, v) in enumerate(_RECALL_OPTIONS):
                if v == self._pending_trigger:
                    self._recall_index = i
                    break
        self._active_group = new
        self._render_all()
        self._feedback.play(Cue.CURSOR)

    def _activate(self) -> None:
        if self._active_group == _RECALL:
            self._stage_recall(self._recall_index)
        elif self._active_group == _COLOR:
            self._stage_color(self._color_cursor.index)
        else:
            if self._action_index == 1:
                self._save()
            else:
                self._cancel()

    # ── Mouse hover (moves the cursor, so mouse and pad agree) ────────────────

    def _bind_hover(self, btn: QPushButton, on_enter: Callable[[], None]) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            on_enter()
        btn.enterEvent = _enter

    def _focus_recall(self, index: int) -> None:
        self._move_focus(_RECALL, changed=self._recall_index != index)
        self._recall_index = index
        self._render_all()

    def _focus_color(self, index: int) -> None:
        self._move_focus(_COLOR, changed=self._color_cursor.index != index)
        self._color_cursor.index = index
        self._render_all()

    def _focus_action(self, index: int) -> None:
        self._move_focus(_ACTIONS, changed=self._action_index != index)
        self._action_index = index
        self._render_all()

    def _move_focus(self, group: int, *, changed: bool) -> None:
        if self._active_group != group or changed:
            self._feedback.play(Cue.CURSOR)
        self._active_group = group

    # ── Staging / committing ─────────────────────────────────────────────────

    def _stage_recall(self, index: int) -> None:
        self._recall_index = index
        self._pending_trigger = _RECALL_OPTIONS[index][1]
        self._render_recall()
        self._feedback.play(Cue.CURSOR)

    def _stage_color(self, index: int) -> None:
        color = self._colors[index]
        if color == self._pending_color:
            return
        self._pending_color = color
        self._refresh_swatches(self._color_cursor.index)
        self._on_color_preview(color)
        self._feedback.play(Cue.CURSOR)

    def _save(self) -> None:
        if self._dismiss(sound=Cue.SELECT):
            self._on_save(self._pending_color, self._pending_trigger)

    def _cancel(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._on_cancel()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render_all(self) -> None:
        self._render_recall()
        self._refresh_swatches(self._color_cursor.index)
        self._render_actions()

    def _render_recall(self) -> None:
        focused = self._active_group == _RECALL
        for i, btn in enumerate(self._recall_buttons):
            role = "selected" if _RECALL_OPTIONS[i][1] == self._pending_trigger \
                else "secondary"
            styles.style_dialog_button(
                btn, role=role, focused=focused and i == self._recall_index)

    def _render_actions(self) -> None:
        # The ring shows only while this group holds the cursor, so Save keeps its
        # primary fill elsewhere instead of looking permanently focused.
        focused = self._active_group == _ACTIONS
        styles.style_dialog_button(
            self._btn_cancel, role="secondary",
            focused=focused and self._action_index == 0)
        styles.style_dialog_button(
            self._btn_save, role="primary",
            focused=focused and self._action_index == 1)

    def _refresh_swatches(self, index: int) -> None:
        focused = self._active_group == _COLOR
        for i, (btn, color) in enumerate(zip(self._swatches, self._colors)):
            is_cursor = i == index
            is_staged = color == self._pending_color
            if is_cursor and focused:
                border = "3px solid white"
            elif is_staged:
                border = f"3px solid {styles.COLOR_ACCENT}"
            else:
                border = "3px solid #888888"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color};"
                f" border: {border}; border-radius: {_SWATCH_RADIUS}px; }}"
            )
