"""Small popover menu shown above a focused tile."""

import logging
from collections.abc import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, QEvent, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtWidgets import QFrame, QWidget, QVBoxLayout, QPushButton, QApplication

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.menu.entry import SEPARATOR
from domain.menu.item import MenuItem
from domain.shared.feedback import Cue, Feedback
from infrastructure.common.qt.ui import styles

logger = logging.getLogger(__name__)


class TilePopoverMenu(QWidget):
    """Small popover menu rendered as a child widget of Desktop, positioned above a tile."""

    closed = pyqtSignal()

    def __init__(
        self,
        items: list[MenuItem],
        on_select: Callable[[MenuItem], None],
        gamepad: PadControl,
        feedback: Feedback,
        parent: QWidget,
        *,
        initial_index: int = 0,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._on_select = on_select
        self._gamepad = gamepad
        self._feedback = feedback
        self._closed = False
        # Vertical menu navigation lives in the domain; this widget owns only
        # presentation. wrap=False — the popover clamps at its ends.
        self._cursor = MenuCursor(
            count=lambda: len(self._items),
            render=self._render_selection,
            on_activate=self._on_btn_clicked,
            on_dismiss=self._dismiss,
            feedback=feedback,
            wrap=False,
            is_selectable=lambda i: self._items[i].action != SEPARATOR,
        )

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setStyleSheet(
            "QWidget { background-color: #2e3440;"
            " border-radius: 10px;"
            " border: 1px solid rgba(255,255,255,18); }"
        )
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(4)
        layout.addWidget(self._card)

        # One widget per item, parallel to `items` so a row index maps straight to
        # an item index. Separators are non-interactive dividers; the cursor skips
        # them, so they never carry the selection highlight.
        self._rows: list[QWidget] = []

        def _bind_hover(btn: QPushButton, idx: int) -> None:
            def _enter(event) -> None:
                QPushButton.enterEvent(btn, event)
                self._on_hover(idx)
            btn.enterEvent = _enter

        for i, item in enumerate(items):
            if item.action == SEPARATOR:
                row = self._make_separator()
            else:
                row = QPushButton(item.label)
                row.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                row.setMinimumWidth(220)
                # Items that carry a glyph (e.g. the power dropdown's
                # sleep/restart/shut-down) show it beside the label; icon-less
                # items (the tile menu) are unchanged.
                if item.icon:
                    row.setIcon(qta.icon(item.icon, color="white"))
                    row.setIconSize(QSize(20, 20))
                row.clicked.connect(lambda checked=False, idx=i: self._on_btn_clicked(idx))
                _bind_hover(row, i)
            card_layout.addWidget(row)
            self._rows.append(row)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Open focused on *initial_index* (e.g. the current default power action),
        # so the dropdown lands on it — highlighted — with no separate marker.
        self._cursor.reset(initial_index)
        self._gamepad.push_handler(self._handle_pad)
        self._feedback.play(Cue.POPUP_OPEN)
        QApplication.instance().installEventFilter(self)

    def show_above(self, tile: QWidget) -> None:
        """Position and display the popover above *tile*."""
        self._show_anchored(tile, below=False)

    def show_below(self, anchor: QWidget, *, gap: int = 12) -> None:
        """Position and display the popover below *anchor* (e.g. a top-bar button,
        which has no room above it). *gap* is the clearance below the anchor."""
        self._show_anchored(anchor, below=True, gap=gap)

    def _show_anchored(self, anchor: QWidget, *, below: bool, gap: int = 12) -> None:
        self.adjustSize()
        anchor_global = anchor.mapToGlobal(QPoint(0, 0))
        parent_global = self.parent().mapToGlobal(QPoint(0, 0))
        ax = anchor_global.x() - parent_global.x()
        ay = anchor_global.y() - parent_global.y()
        x = ax + (anchor.width() - self.width()) // 2
        y = ay + anchor.height() + gap if below else ay - self.height() - gap
        self.move(x, max(0, y))
        self.show()
        self.raise_()
        self.setFocus()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        # X (CLOSE) opened this menu; Y (ACTIONS) also toggles it closed.
        if event in (Event.CLOSE, Event.ACTIONS):
            self._dismiss()
            return
        self._cursor.handle_pad(event)

    # ── Internal ───────────────────────────────────────────────────────────

    def _dismiss(self, play_sound: bool = True) -> None:
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handle_pad)
            QApplication.instance().removeEventFilter(self)
            if play_sound:
                self._feedback.play(Cue.POPUP_CLOSE)
            self.closed.emit()
            self.hide()
            self.deleteLater()

    _KEY_MAP = {
        Qt.Key.Key_Up:     Event.UP,
        Qt.Key.Key_Down:   Event.DOWN,
        Qt.Key.Key_Return: Event.SELECT,
        Qt.Key.Key_Enter:  Event.SELECT,
        Qt.Key.Key_Escape: Event.CANCEL,
        Qt.Key.Key_Q:      Event.CANCEL,
    }

    def keyPressEvent(self, event) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._handle_pad(mapped)   # same path as the pad (ACTIONS toggles closed)

    def eventFilter(self, obj, event) -> bool:
        if (event.type() == QEvent.Type.MouseButtonPress
                and not self._closed
                and isinstance(obj, QWidget)):
            click_global = obj.mapToGlobal(event.pos())
            our_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
            if not our_rect.contains(click_global):
                self._dismiss()
        return False

    def _on_btn_clicked(self, idx: int) -> None:
        item = self._items[idx]
        self._dismiss(play_sound=False)
        self._on_select(item)

    def _on_hover(self, idx: int) -> None:
        self._cursor.hover(idx)

    def pause(self) -> None:
        if not self._closed:
            self._gamepad.pop_handler(self._handle_pad)

    def resume(self) -> None:
        if not self._closed:
            self._gamepad.push_handler(self._handle_pad)

    def cancel(self) -> None:
        if not self._closed:
            self._gamepad.pop_handler(self._handle_pad)
            self._closed = True
            self.hide()
            self.deleteLater()

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: rgba(255,255,255,28); border: none;")
        return line

    def _render_selection(self, index: int) -> None:
        for i, row in enumerate(self._rows):
            if not isinstance(row, QPushButton):
                continue   # separators never highlight
            row.setStyleSheet(
                styles.home_menu_item_selected() if i == index
                else styles.home_menu_item_normal()
            )
