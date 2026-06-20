"""Tile popover stub for Windows."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

logger = logging.getLogger(__name__)


class TilePopoverMenu(QWidget):
    """Stub tile popover - shows a vertical menu of items."""

    closed = pyqtSignal()

    def __init__(self, items, on_select, gamepad, feedback, parent=None):
        super().__init__(parent)
        self._items = items
        self._on_select = on_select
        self._gamepad = gamepad
        self._feedback = feedback
        self._selected = 0
        self._btns = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        for i, item in enumerate(self._items):
            btn = QPushButton("  " + item.label)
            btn.setMinimumHeight(50)
            btn.clicked.connect(lambda _, idx=i: self._activate(idx))
            btn.setStyleSheet(self._normal_style())
            layout.addWidget(btn)
            self._btns.append(btn)
        self._render_selection()

    def _normal_style(self) -> str:
        return """
            QPushButton {
                font-size: 20px;
                padding: 14px 24px;
                background-color: #2e3440;
                color: white;
                border: 2px solid transparent;
                text-align: left;
            }
        """

    def _selected_style(self) -> str:
        return """
            QPushButton {
                font-size: 20px;
                padding: 14px 24px;
                background-color: #88c0d0;
                color: black;
                border: 2px solid white;
                text-align: left;
            }
        """

    def _render_selection(self) -> None:
        for i, btn in enumerate(self._btns):
            btn.setStyleSheet(self._selected_style() if i == self._selected else self._normal_style())

    def _activate(self, idx: int) -> None:
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()
        if self._on_select:
            self._on_select(self._items[idx])
        self.closed.emit()

    def show_above(self, tile) -> None:
        if tile is None:
            return
        from PyQt6.QtCore import QTimer
        pos = tile.mapToGlobal(tile.rect().topLeft())
        self.move(pos.x() - 50, pos.y() - self.height() - 10)
        self.show()
        QTimer.singleShot(0, lambda: self._gamepad.push_handler(self._handle_pad))

    def _handle_pad(self, event: str) -> None:
        from domain.input.vocabulary import Event
        if event in (Event.UP, Event.LEFT):
            self._selected = (self._selected - 1) % max(1, len(self._items))
            self._render_selection()
        elif event in (Event.DOWN, Event.RIGHT):
            self._selected = (self._selected + 1) % max(1, len(self._items))
            self._render_selection()
        elif event == Event.SELECT:
            self._activate(self._selected)
        elif event == Event.CANCEL:
            self._close()

    def _close(self) -> None:
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event) -> None:
        from domain.input.vocabulary import Event
        mapped = {
            Qt.Key.Key_Up: Event.UP,
            Qt.Key.Key_Down: Event.DOWN,
            Qt.Key.Key_Return: Event.SELECT,
            Qt.Key.Key_Escape: Event.CANCEL,
        }.get(event.key())
        if mapped:
            self._handle_pad(mapped)
        super().keyPressEvent(event)

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass