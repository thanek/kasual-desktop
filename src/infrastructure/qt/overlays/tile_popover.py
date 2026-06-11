"""Small popover menu shown above a focused tile."""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QEvent, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QApplication

from domain.menu.cursor import MenuCursor
from domain.menu.item import MenuItem
from domain.input.vocabulary import Event
from infrastructure.audio import sound_player
from infrastructure.audio.feedback import SoundFeedback
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.ui import styles

logger = logging.getLogger(__name__)


class TilePopoverMenu(QWidget):
    """Small popover menu rendered as a child widget of Desktop, positioned above a tile."""

    closed = pyqtSignal()

    def __init__(
        self,
        items: list[MenuItem],
        on_select: Callable[[MenuItem], None],
        gamepad: GamepadWatcher,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._on_select = on_select
        self._gamepad = gamepad
        self._closed = False
        # Vertical menu navigation lives in the domain; this widget owns only
        # presentation. wrap=False — the popover clamps at its ends.
        self._cursor = MenuCursor(
            count=lambda: len(self._items),
            render=self._render_selection,
            on_activate=self._on_btn_clicked,
            on_dismiss=self._dismiss,
            feedback=SoundFeedback(),
            wrap=False,
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

        self._buttons: list[QPushButton] = []

        def _bind_hover(btn: QPushButton, idx: int) -> None:
            def _enter(event) -> None:
                QPushButton.enterEvent(btn, event)
                self._on_hover(idx)
            btn.enterEvent = _enter

        for i, item in enumerate(items):
            btn = QPushButton(item.label)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setMinimumWidth(220)
            btn.clicked.connect(lambda checked=False, idx=i: self._on_btn_clicked(idx))
            _bind_hover(btn, i)
            card_layout.addWidget(btn)
            self._buttons.append(btn)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._cursor.reset(0)
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("popup_open")
        QApplication.instance().installEventFilter(self)

    def show_above(self, tile: QWidget) -> None:
        """Position and display the popover above *tile*."""
        self.adjustSize()
        tile_global = tile.mapToGlobal(QPoint(0, 0))
        parent_global = self.parent().mapToGlobal(QPoint(0, 0))
        tile_x = tile_global.x() - parent_global.x()
        tile_y = tile_global.y() - parent_global.y()
        x = tile_x + (tile.width() - self.width()) // 2
        y = tile_y - self.height() - 12
        self.move(x, max(0, y))
        self.show()
        self.raise_()
        self.setFocus()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    # ── Internal ───────────────────────────────────────────────────────────

    def _dismiss(self, play_sound: bool = True) -> None:
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handle_pad)
            QApplication.instance().removeEventFilter(self)
            if play_sound:
                sound_player.play("popup_close")
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
            self._cursor.handle_pad(mapped)

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

    def _render_selection(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            if i == index:
                btn.setStyleSheet(styles.home_menu_item_selected())
            else:
                btn.setStyleSheet(styles.home_menu_item_normal())
