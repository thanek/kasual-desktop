"""Fullscreen overlay for picking a tile colour from a fixed palette.

Shown from the Tile Management Popover's *Change color* action. A grid of colour
swatches (at most ``_MAX_PER_ROW`` per row) navigated up/down/left/right;
selecting one recolours the tile, cancelling (B / Escape / backdrop) leaves it
unchanged. As a registered layer-shell overlay it is torn down by the group
dismiss when BTN_MODE summons the Home Overlay.
"""

from collections.abc import Callable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.grid_cursor import GridCursor
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from .base_overlay import BaseOverlay

_SWATCH = 88        # swatch side, px
_SWATCH_RADIUS = 16
_SWATCH_GAP = 16    # spacing between swatches, px
_MAX_PER_ROW = 10   # wrap the palette into rows of at most this many swatches


class TileColorPicker(BaseOverlay):
    """Modal palette picker. Calls *on_select(color)* on choice, *on_cancel* otherwise."""

    def __init__(
        self,
        colors: Sequence[str],
        selected: str | None,
        on_select: Callable[[str], None],
        on_cancel: Callable[[], None],
        gamepad: PadControl,
        feedback: Feedback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(gamepad, self._handle_pad, feedback, parent)
        self._colors = list(colors)
        self._on_select = on_select
        self._on_cancel = on_cancel
        # Grid navigation over the swatches (up/down/left/right); wraps on both axes.
        self._cursor = GridCursor(
            count=lambda: len(self._colors),
            columns=_MAX_PER_ROW,
            render=self._refresh_swatches,
            on_activate=self._on_activate,
            on_dismiss=self._cancel,
            feedback=feedback,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        per_row = min(len(self._colors), _MAX_PER_ROW)
        card = self.build_card(160 + per_row * (_SWATCH + _SWATCH_GAP))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(28)

        title = QLabel(translate("Desktop", "Change color"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(_SWATCH_GAP)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._swatches: list[QPushButton] = []
        for i, color in enumerate(self._colors):
            btn = QPushButton()
            btn.setFixedSize(_SWATCH, _SWATCH)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _checked=False, idx=i: self._on_activate(idx))
            grid.addWidget(btn, i // _MAX_PER_ROW, i % _MAX_PER_ROW)
            self._swatches.append(btn)
        layout.addLayout(grid)

        outer.addWidget(card)

        start = self._colors.index(selected) if selected in self._colors else 0
        self._cursor.reset(start)
        self._feedback.play(Cue.POPUP_OPEN)
        self._show()

    # ── Gamepad ──────────────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    # ── Keyboard / mouse ─────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._cancel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._cursor.handle_pad(Event.SELECT)
        elif key == Qt.Key.Key_Escape:
            self._cursor.handle_pad(Event.CANCEL)
        elif key == Qt.Key.Key_Left:
            self._cursor.handle_pad(Event.LEFT)
        elif key == Qt.Key.Key_Right:
            self._cursor.handle_pad(Event.RIGHT)
        elif key == Qt.Key.Key_Up:
            self._cursor.handle_pad(Event.UP)
        elif key == Qt.Key.Key_Down:
            self._cursor.handle_pad(Event.DOWN)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_activate(self, index: int) -> None:
        color = self._colors[index]
        if self._dismiss(sound=Cue.SELECT):
            self._on_select(color)

    def _cancel(self) -> None:
        if self._dismiss(sound=Cue.POPUP_CLOSE):
            self._on_cancel()

    def _refresh_swatches(self, index: int) -> None:
        for i, (btn, color) in enumerate(zip(self._swatches, self._colors)):
            border = "3px solid white" if i == index else "3px solid #888888"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color};"
                f" border: {border}; border-radius: {_SWATCH_RADIUS}px; }}"
            )
