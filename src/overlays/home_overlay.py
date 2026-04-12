import logging
import subprocess
from typing import Callable, NotRequired, TypedDict

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QLabel,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QKeyEvent

import qtawesome as qta

from input.gamepad_watcher import GamepadWatcher
from .confirm_dialog import ConfirmDialog
from ui import styles
from system.system_actions import SYSTEM_ACTION_SPECS
from audio import sound_player

logger = logging.getLogger(__name__)


class MenuItem(TypedDict):
    label: str
    icon:  str
    action:   NotRequired[str]       # dla pozycji statycznych (_STATIC_ITEMS)
    callback: NotRequired[Callable]  # dla pozycji dynamicznych (extra_items)


_STATIC_ITEMS: list[MenuItem] = [
    {"label": "  Powrót do Pulpitu",    "icon": "fa5s.times",          "action": "cancel"},
    {"label": "  Minimalizuj Pulpit",   "icon": "fa5s.window-minimize", "action": "hide_desktop"},
    {"label": "  Uśpij system",         "icon": "fa5s.moon",            "action": "sleep"},
    {"label": "  Zrestartuj komputer",  "icon": "fa5s.redo-alt",        "action": "restart"},
    {"label": "  Zamknij system",       "icon": "fa5s.power-off",       "action": "shutdown"},
]


class HomeOverlay(QWidget):
    """
    Fullscreen overlay pokazywany po wciśnięciu BTN_MODE.

    Niezależne top-level okno (nie child Desktop) z WindowStaysOnTopHint –
    przykrywa wszystko, łącznie z fullscreen aplikacjami.

    Użycie:
        overlay = HomeOverlay(gamepad)
        overlay.show_overlay(extra_items=[...])   # pokazuje z kontekstem
        overlay.hide_overlay()                    # chowa
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
            | Qt.WindowType.Tool          # nie pojawia się na taskbarze
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

        title = QLabel("Menu")
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

    # ── Tło ────────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 170))

    # ── Publiczne API ──────────────────────────────────────────────────────

    def show_overlay(
        self,
        extra_items: list[MenuItem] | None = None,
        on_cancel=None,
    ) -> None:
        """
        Pokaż overlay z dynamicznym menu.

        extra_items – lista dict z kluczami: label, icon, callback.
        Wstawiane na szczycie listy przed opcjami systemowymi.
        on_cancel – callback wywoływany po wybraniu "Anuluj" w trybie desktop.
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
        """Zamknij overlay i przywróć poprzedni kontekst (on_cancel)."""
        sound_player.play("popup_close")
        self.hide_overlay()
        if self._on_cancel:
            self._on_cancel()

    # ── Budowanie menu ─────────────────────────────────────────────────────

    def _rebuild_buttons(self, extra_items: list[MenuItem]) -> None:
        while self._buttons_layout.count():
            item = self._buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

        self._items = list(extra_items) if extra_items else list(_STATIC_ITEMS)

        for item in self._items:
            btn = QPushButton(item["label"])
            btn.setMinimumHeight(62)
            btn.setIcon(qta.icon(item["icon"], color="white"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._buttons_layout.addWidget(btn)
            self._buttons.append(btn)

    # ── Handler pada ───────────────────────────────────────────────────────

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

    # ── Klawiatura ─────────────────────────────────────────────────────────

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

    # ── Akcje ──────────────────────────────────────────────────────────────

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
        question, cmd = SYSTEM_ACTION_SPECS[action]
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

    # ── Styl ───────────────────────────────────────────────────────────────

    def _refresh_buttons(self) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                styles.home_menu_item_selected() if i == self._index
                else styles.home_menu_item_normal()
            )
