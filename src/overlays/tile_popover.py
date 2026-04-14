"""Small popover menu shown above a focused tile."""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from ui import styles

logger = logging.getLogger(__name__)


class TilePopoverMenu(QWidget):
    """Small popover menu rendered as a child widget of Desktop, positioned above a tile."""

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

        card = QWidget()
        card.setStyleSheet(
            "QWidget { background-color: #2e3440;"
            " border-radius: 10px;"
            " border: 1px solid rgba(255,255,255,18); }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(4)
        layout.addWidget(card)

        self._buttons: list[QPushButton] = []
        for label, _ in options:
            btn = QPushButton(label)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setMinimumWidth(220)
            card_layout.addWidget(btn)
            self._buttons.append(btn)

        self._refresh_style()
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("popup_open")

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

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == "up" and self._idx > 0:
            self._idx -= 1
            self._refresh_style()
            sound_player.play("cursor")
        elif event == "down" and self._idx < len(self._options) - 1:
            self._idx += 1
            self._refresh_style()
            sound_player.play("cursor")
        elif event == "select":
            _, callback = self._options[self._idx]
            self._dismiss(play_sound=False)
            callback()
        elif event in ("cancel", "close"):
            self._dismiss()

    # ── Internal ───────────────────────────────────────────────────────────

    def _dismiss(self, play_sound: bool = True) -> None:
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handle_pad)
            if play_sound:
                sound_player.play("popup_close")
            self.hide()
            self.deleteLater()

    def _refresh_style(self) -> None:
        for i, btn in enumerate(self._buttons):
            if i == self._idx:
                btn.setStyleSheet(styles.home_menu_item_selected())
            else:
                btn.setStyleSheet(styles.home_menu_item_normal())
