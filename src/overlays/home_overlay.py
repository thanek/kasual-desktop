import logging
import subprocess
from typing import Callable, NotRequired, TypedDict

import qtawesome as qta
from PyQt6.QtCore import Qt, QCoreApplication, QT_TRANSLATE_NOOP
from PyQt6.QtGui import QColor, QPainter, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QLabel,
    QGraphicsDropShadowEffect,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from system.system_actions import SYSTEM_ACTION_SPECS
from ui import styles
from .confirm_dialog import ConfirmDialog

logger = logging.getLogger(__name__)


class MenuItem(TypedDict):
    label: str
    icon:  str
    action:   NotRequired[str]       # for static items (_STATIC_ITEMS)
    callback: NotRequired[Callable]  # for dynamic items (extra_items)


# Labels marked with QT_TRANSLATE_NOOP — extracted by pylupdate6,
# and translated only when building buttons in _rebuild_buttons().
_STATIC_ITEMS: list[MenuItem] = [
    {"label": QT_TRANSLATE_NOOP("Kasual", "Return to Desktop"),  "icon": "fa5s.times",          "action": "cancel"},
    {"label": QT_TRANSLATE_NOOP("Kasual", "Minimize Desktop"),   "icon": "fa5s.window-minimize", "action": "hide_desktop"},
    {"label": QT_TRANSLATE_NOOP("Kasual", "Sleep"),              "icon": "fa5s.moon",            "action": "sleep"},
    {"label": QT_TRANSLATE_NOOP("Kasual", "Restart"),            "icon": "fa5s.redo-alt",        "action": "restart"},
    {"label": QT_TRANSLATE_NOOP("Kasual", "Shut Down"),          "icon": "fa5s.power-off",       "action": "shutdown"},
]


class HomeOverlay(QWidget):
    """
    Fullscreen overlay shown when BTN_MODE is pressed.

    An independent top-level window (not a child of Desktop) with WindowStaysOnTopHint —
    covers everything, including fullscreen applications.

    Usage:
        overlay = HomeOverlay(gamepad)
        overlay.show_overlay(extra_items=[...])   # show with context
        overlay.hide_overlay()                    # hide
    """

    def __init__(self, gamepad: GamepadWatcher, on_hide_desktop: Callable | None = None, parent=None):
        super().__init__(parent)
        self._gamepad          = gamepad
        self._on_hide_desktop  = on_hide_desktop
        self._index            = 0
        self._items:     list[MenuItem]    = []
        self._buttons:   list[QPushButton] = []
        self._on_cancel  = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool          # does not appear on the taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = QWidget()
        self._card.setFixedWidth(500)
        self._card.setStyleSheet("background-color: #1e2430; border-radius: 14px;")

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(32, 32, 32, 32)
        self._card_layout.setSpacing(8)

        title = QLabel(self.tr("Menu"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; color: #88c0d0; font-weight: bold;"
            " background: transparent; padding-bottom: 8px;"
        )
        self._card_layout.addWidget(title)

        self._buttons_container = QWidget()
        self._buttons_container.setStyleSheet("background: transparent;")
        self._buttons_layout = QVBoxLayout(self._buttons_container)
        self._buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._buttons_layout.setSpacing(8)
        self._card_layout.addWidget(self._buttons_container)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setBlurRadius(50)
        self._card.setGraphicsEffect(shadow)

        outer.addWidget(self._card)

    # ── Background ─────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))

    # ── Public API ─────────────────────────────────────────────────────────

    def show_overlay(
        self,
        extra_items: list[MenuItem] | None = None,
        on_cancel=None,
    ) -> None:
        """
        Show overlay with a dynamic menu.

        extra_items — list of dicts with keys: label, icon, callback.
        Inserted at the top of the list before system options.
        on_cancel — callback invoked when "Cancel" is chosen in desktop mode.
        """
        if self.isVisible():
            return
        self._on_cancel = on_cancel
        self._rebuild_buttons(extra_items or [])
        self._index = 0
        self._refresh_buttons()
        self._gamepad.push_handler(self._handle_pad)
        sound_player.play("popup_open")
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def hide_overlay(self) -> None:
        if not self.isVisible():
            return
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()

    def _dismiss(self) -> None:
        """Close the overlay and restore the previous context (on_cancel)."""
        sound_player.play("popup_close")
        self.hide_overlay()
        if self._on_cancel:
            self._on_cancel()

    # ── Building menu ──────────────────────────────────────────────────────

    def _rebuild_buttons(self, extra_items: list[MenuItem]) -> None:
        while self._buttons_layout.count():
            item = self._buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

        self._items = list(extra_items) if extra_items else list(_STATIC_ITEMS)

        for item in self._items:
            # Static items have labels marked with QT_TRANSLATE_NOOP — we translate here.
            # Dynamic items (callback) already have ready-formatted labels.
            label = (
                "  " + QCoreApplication.translate("Kasual", item["label"])
                if "action" in item
                else item["label"]
            )
            btn = QPushButton(label)
            btn.setMinimumHeight(62)
            btn.setIcon(qta.icon(item["icon"], color="white"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._buttons_layout.addWidget(btn)
            self._buttons.append(btn)

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == "up":
            self._index = (self._index - 1) % len(self._items)
            self._refresh_buttons()
            sound_player.play("cursor")
        elif event == "down":
            self._index = (self._index + 1) % len(self._items)
            self._refresh_buttons()
            sound_player.play("cursor")
        elif event == "select":
            self._activate(self._index)
        elif event in ("cancel", "close"):
            self._dismiss()

    # ── Keyboard ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Up:
            self._index = (self._index - 1) % len(self._items)
            self._refresh_buttons()
        elif key == Qt.Key.Key_Down:
            self._index = (self._index + 1) % len(self._items)
            self._refresh_buttons()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate(self._index)
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_F1):
            self._dismiss()

    # ── Actions ────────────────────────────────────────────────────────────

    def _activate(self, idx: int) -> None:
        item = self._items[idx]

        if "callback" in item:
            sound_player.play("select")
            self.hide_overlay()
            item["callback"]()
            return

        action = item["action"]
        if action == "cancel":
            sound_player.play("popup_close")
            self.hide_overlay()
            if self._on_cancel:
                self._on_cancel()
            return

        if action not in SYSTEM_ACTION_SPECS:
            return
        question_src, cmd = SYSTEM_ACTION_SPECS[action]
        question = QCoreApplication.translate("Kasual", question_src)
        on_confirmed = (
            self._on_hide_desktop if cmd is None
            else (lambda c=cmd: subprocess.Popen(c))
        )
        self.hide_overlay()
        if on_confirmed is None:
            return
        ConfirmDialog(
            question=question,
            on_confirmed=on_confirmed,
            on_cancelled=lambda: None,
            gamepad=self._gamepad,
        )

    # ── Style ──────────────────────────────────────────────────────────────

    def _refresh_buttons(self) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                styles.home_menu_item_selected() if i == self._index
                else styles.home_menu_item_normal()
            )
