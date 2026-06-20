"""
Minimal HomeOverlay skeleton for the Windows PoC.

A simple PyQt window that demonstrates the overlay concept.
"""

import logging
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class HomeOverlay(QWidget):
    """
    Minimal Home Overlay that displays on top of the shell.

    On Linux this would be a layer-shell surface.
    On Windows it's just a topmost widget within our shell.
    """

    def __init__(
        self,
        on_select: Callable[[str], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._buttons: list[QPushButton] = []
        self._selected_index = 0
        self._setup_ui()
        self._highlight_selection()

    def _setup_ui(self):
        self.setWindowTitle("Home Overlay")
        self.resize(800, 600)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)

        desktop = QApplication.primaryScreen().geometry()
        self.move(
            (desktop.width() - self.width()) // 2,
            (desktop.height() - self.height()) // 2,
        )

        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2a;
                color: white;
            }
            QPushButton {
                padding: 12px 24px;
                font-size: 16px;
                background-color: #3a3a4a;
                color: white;
                border: 2px solid #5a5a6a;
                border-radius: 8px;
                min-width: 200px;
            }
            QPushButton:pressed {
                background-color: #2a2a3a;
            }
        """)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("Kasual Desktop")
        title.setStyleSheet("font-size: 32px; font-weight: bold; padding: 20px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Press BTN_MODE (Xbox button) or ESC to close")
        subtitle.setStyleSheet("font-size: 14px; color: #888;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(40)

        btn_container = QWidget()
        btn_layout = QVBoxLayout()
        btn_container.setLayout(btn_layout)

        actions = [
            ("Przywróć Kasual", "restore"),
            ("Minimalizuj Kasual", "minimize"),
            ("Zamknij aplikację", "exit"),
        ]
        self._actions = actions

        for label, action in actions:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, a=action: self._handle_action(a))
            btn_layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addWidget(btn_container)

        self.setLayout(layout)

    def _highlight_selection(self):
        for i, btn in enumerate(self._buttons):
            if i == self._selected_index:
                btn.setStyleSheet("""
                    QPushButton {
                        padding: 12px 24px;
                        font-size: 16px;
                        background-color: #6ab04c;
                        color: white;
                        border: 2px solid #8ae86c;
                        border-radius: 8px;
                        min-width: 200px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        padding: 12px 24px;
                        font-size: 16px;
                        background-color: #3a3a4a;
                        color: white;
                        border: 1px solid #5a5a6a;
                        border-radius: 8px;
                        min-width: 200px;
                    }
                """)

    def handle_navigation(self, event: str):
        logger.debug("handle_navigation called with: %s", event)
        from domain.input.vocabulary import Event
        if event in (Event.UP, Event.LEFT):
            self._selected_index = (self._selected_index - 1) % len(self._buttons)
            self._highlight_selection()
        elif event in (Event.DOWN, Event.RIGHT):
            self._selected_index = (self._selected_index + 1) % len(self._buttons)
            self._highlight_selection()
        elif event == Event.SELECT:
            action = self._actions[self._selected_index][1]
            self._handle_action(action)
        elif event == Event.CANCEL:
            if self._on_cancel:
                self._on_cancel()
            self.hide()

    def _handle_action(self, action: str):
        logger.info("Action selected: %s", action)
        if action == "restore":
            from infrastructure.windows.desktop_shell import get_desktop_shell
            get_desktop_shell().restore()
        elif action == "minimize":
            from infrastructure.windows.desktop_shell import get_desktop_shell
            get_desktop_shell().pause()
        elif action == "exit":
            if self._on_cancel:
                self._on_cancel()
        else:
            if self._on_select:
                self._on_select(action)
        self.hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self._on_cancel:
                self._on_cancel()
            self.hide()
        super().keyPressEvent(event)

    def show_overlay(self):
        logger.debug("show_overlay called")
        self._selected_index = 0
        self._highlight_selection()
        self.show()
        self.activateWindow()
        self.raise_()
        logger.debug("Overlay shown, isVisible=%s", self.isVisible())

    def hide_overlay(self):
        self.hide()


class HomeOverlayFactory:
    """Factory for creating HomeOverlay instances."""

    def __init__(self, gamepad, feedback=None):
        self._gamepad = gamepad
        self._feedback = feedback

    def create(self) -> QWidget:
        return HomeOverlay()


def compose_home_menu(apps=None, hud_control=None, foreground_is_game=False):
    """
    Compose the home menu items.

    Simplified version for PoC.
    """
    return HomeMenuItems(
        items=[
            ("resume", "Resume Game", "back"),
            ("settings", "Settings", "gear"),
            ("exit", "Exit to Windows", "power"),
        ],
        cancel_restores=None,
    )


class HomeMenuItems:
    def __init__(self, items, cancel_restores):
        self.items = items  # list of (action_id, label, icon)
        self.cancel_restores = cancel_restores