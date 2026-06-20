"""Home Overlay for Windows - full menu with MenuItems mirroring Linux."""

import logging
from typing import Callable

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.menu.home import HomeMenu, compose_home_menu
from domain.menu.item import MenuItem
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate

logger = logging.getLogger(__name__)

COLOR_ACCENT = "#88c0d0"


def _home_menu_item_normal() -> str:
    return """
        QPushButton {
            font-size: 24px;
            padding: 18px 32px;
            background-color: #2e3440;
            color: white;
            border: 2px solid transparent;
            text-align: left;
        }
    """


def _home_menu_item_selected() -> str:
    return f"""
        QPushButton {{
            font-size: 24px;
            padding: 18px 32px;
            background-color: {COLOR_ACCENT};
            color: black;
            border: 2px solid white;
            text-align: left;
        }}
    """


class WindowsHomeOverlay(QWidget):
    """Home Overlay for Windows - mirrors Linux HomeOverlay."""

    closed = pyqtSignal()

    def __init__(self, gamepad: PadControl, feedback: Feedback, parent=None):
        super().__init__(parent)
        self._gamepad = gamepad
        self._feedback = feedback
        self._on_select: Callable[[MenuItem], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._buttons: list[QPushButton] = []
        self._items: list[MenuItem] = []
        self._cursor: MenuCursor | None = None
        self._hud = _StubHudControl()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = QWidget()
        self._card.setFixedWidth(500)
        self._card.setStyleSheet("""
            background-color: #2e3440;
            border-radius: 12px;
        """)
        self._apply_shadow()

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(32, 32, 32, 32)
        self._card_layout.setSpacing(8)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._title = QLabel("Kasual Desktop")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet(
            "font-size: 28px; color: #88c0d0; font-weight: bold;"
            " background: transparent; padding-bottom: 8px;"
        )
        self._card_layout.addWidget(self._title)

        self._buttons_container = QWidget()
        self._buttons_container.setStyleSheet("background: transparent;")
        self._buttons_layout = QVBoxLayout(self._buttons_container)
        self._buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._buttons_layout.setSpacing(8)
        self._card_layout.addWidget(self._buttons_container)

        outer.addWidget(self._card)

    def _apply_shadow(self) -> None:
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        effect = QGraphicsDropShadowEffect(self._card)
        effect.setOffset(0, 0)
        effect.setBlurRadius(90)
        effect.setColor(QColor(0, 0, 0, 180))
        self._card.setGraphicsEffect(effect)

    def show_overlay(
        self,
        items: list[MenuItem] | None = None,
        on_select: Callable[[MenuItem], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        foreground_is_game: bool = False,
    ) -> None:
        if self.isVisible():
            return
        self._on_select = on_select
        self._on_cancel = on_cancel

        if items is None:
            menu = compose_home_menu(foreground=None, hud=self._hud, foreground_is_game=foreground_is_game)
            items = menu.items

        self._rebuild_buttons(items)
        self._gamepad.push_handler(self._handle_pad)
        self._show()
        logger.debug("HomeOverlay shown")

    def _show(self) -> None:
        self.showFullScreen()
        self.raise_()

    def hide_overlay(self) -> None:
        if not self.isVisible():
            return
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()
        self.closed.emit()

    def _handle_pad(self, event: str) -> None:
        if self._cursor:
            self._cursor.handle_pad(event)

    def _rebuild_buttons(self, items: list[MenuItem]) -> None:
        while self._buttons_layout.count():
            item = self._buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()
        self._items = list(items)

        self._cursor = MenuCursor(
            count=lambda: len(self._items),
            render=self._render_selection,
            on_activate=self._activate,
            on_dismiss=self._dismiss,
            feedback=self._feedback,
            wrap=True,
        )

        for i, item in enumerate(self._items):
            btn = QPushButton("  " + item.label)
            btn.setMinimumHeight(62)
            if item.icon:
                try:
                    btn.setIcon(qta.icon(item.icon, color="white"))
                except Exception:
                    pass
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked=False, idx=i: self._activate(idx))
            self._bind_hover(btn, i)
            self._buttons_layout.addWidget(btn)
            self._buttons.append(btn)

        self._cursor.reset(0)

    def _bind_hover(self, btn: QPushButton, idx: int) -> None:
        def _enter(event) -> None:
            QPushButton.enterEvent(btn, event)
            if self._cursor:
                self._cursor.hover(idx)
        btn.enterEvent = _enter

    def _render_selection(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                _home_menu_item_selected() if i == index
                else _home_menu_item_normal()
            )

    def _activate(self, idx: int) -> None:
        item = self._items[idx]
        self._feedback.play(Cue.SELECT)
        self.hide_overlay()
        if self._on_select is not None:
            self._on_select(item)

    def _dismiss(self) -> None:
        self._feedback.play(Cue.POPUP_CLOSE)
        self.hide_overlay()
        if self._on_cancel:
            self._on_cancel()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = None
        if event.key() == Qt.Key.Key_Up:
            mapped = Event.UP
        elif event.key() == Qt.Key.Key_Down:
            mapped = Event.DOWN
        elif event.key() == Qt.Key.Key_Return:
            mapped = Event.SELECT
        elif event.key() == Qt.Key.Key_Enter:
            mapped = Event.SELECT
        elif event.key() == Qt.Key.Key_Escape:
            self._dismiss()
            return
        elif event.key() == Qt.Key.Key_F1:
            self._dismiss()
            return

        if mapped and self._cursor:
            self._cursor.handle_pad(mapped)

    def mousePressEvent(self, event) -> None:
        if not self._card.geometry().contains(event.pos()):
            self._dismiss()
        else:
            super().mousePressEvent(event)


class _StubHudControl:
    """Stub HudControl - HUD is not implemented in Windows Iteracja 1."""

    def is_configured(self) -> bool:
        return False

    def is_visible(self) -> bool:
        return False

    def toggle(self) -> None:
        pass


class WindowsHomeOverlayFactory:
    """Factory for creating Windows HomeOverlay instances."""

    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback

    def create_home_overlay(self) -> WindowsHomeOverlay:
        return WindowsHomeOverlay(self._gamepad, self._feedback)