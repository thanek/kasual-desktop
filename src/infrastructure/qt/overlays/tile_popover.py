"""Small popover menu shown above a focused tile."""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QEvent, QPoint, QRect, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QApplication

from domain.input import Event
from infrastructure.audio import sound_player
from infrastructure.input.gamepad_watcher import GamepadWatcher
from infrastructure.qt.ui import styles

logger = logging.getLogger(__name__)


class TilePopoverMenu(QWidget):
    """Small popover menu rendered as a child widget of Desktop, positioned above a tile."""

    closed = pyqtSignal()

    def __init__(
        self,
        options: list[tuple[str, Callable[[], None]]],
        gamepad: GamepadWatcher,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._options = options
        self._gamepad = gamepad
        self._idx = 0
        self._closed = False

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

        for i, (label, _) in enumerate(options):
            btn = QPushButton(label)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setMinimumWidth(220)
            btn.clicked.connect(lambda checked=False, idx=i: self._on_btn_clicked(idx))
            _bind_hover(btn, i)
            card_layout.addWidget(btn)
            self._buttons.append(btn)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._refresh_style()
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
        if event == Event.UP and self._idx > 0:
            self._idx -= 1
            self._refresh_style()
            sound_player.play("cursor")
        elif event == Event.DOWN and self._idx < len(self._options) - 1:
            self._idx += 1
            self._refresh_style()
            sound_player.play("cursor")
        elif event == Event.SELECT:
            _, callback = self._options[self._idx]
            self._dismiss(play_sound=False)
            callback()
        elif event in (Event.CANCEL, Event.CLOSE):
            self._dismiss()

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

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up and self._idx > 0:
            self._idx -= 1
            self._refresh_style()
            sound_player.play("cursor")
        elif key == Qt.Key.Key_Down and self._idx < len(self._options) - 1:
            self._idx += 1
            self._refresh_style()
            sound_player.play("cursor")
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            _, callback = self._options[self._idx]
            self._dismiss(play_sound=False)
            callback()
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self._dismiss()

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
        _, callback = self._options[idx]
        self._dismiss(play_sound=False)
        callback()

    def _on_hover(self, idx: int) -> None:
        if self._idx != idx:
            self._idx = idx
            self._refresh_style()
            sound_player.play("cursor")

    def _refresh_style(self) -> None:
        for i, btn in enumerate(self._buttons):
            if i == self._idx:
                btn.setStyleSheet(styles.home_menu_item_selected())
            else:
                btn.setStyleSheet(styles.home_menu_item_normal())
