import logging
from typing import Callable, NotRequired, TypedDict

import qtawesome as qta
from PyQt6.QtCore import Qt, QCoreApplication, QT_TRANSLATE_NOOP, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from system.system_actions import ACTIONS, ActionDeps, ActionRunner
from ui import styles
from ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard
from .confirm_dialog import ConfirmDialog

logger = logging.getLogger(__name__)


class MenuItem(TypedDict):
    label: str
    icon:  str
    action:   NotRequired[str]       # for static items (_STATIC_ITEMS)
    callback: NotRequired[Callable]  # for dynamic items (extra_items)


class HomeOverlay(QWidget):
    """
    Full-screen menu overlay shown when BTN_MODE is pressed.

    A standalone wlr-layer-shell surface in the `overlay` layer, so it sits
    above everything — the KD Desktop, normal windows, and fullscreen games —
    without touching what is underneath. Its translucent backdrop lets the live
    screen show through; the menu card is anchored to the right edge (sidebar).

    Usage:
        overlay = HomeOverlay(gamepad, action_deps)
        overlay.show_overlay(items=[...])         # show with context
        overlay.hide_overlay()                    # hide
    """

    closed = pyqtSignal()   # emitted when the overlay is dismissed


    @staticmethod
    def static_items() -> list[MenuItem]:
        cancel_item: MenuItem = {
            "label": QT_TRANSLATE_NOOP("Kasual", "Return to Desktop"),
            "icon": "fa5s.times",
            "action": "cancel",
        }
        return [cancel_item] + [
            {"label": spec["label"], "icon": spec["icon"], "action": action_type}
            for action_type, spec in ACTIONS.items()
        ]

    def __init__(
        self,
        gamepad: GamepadWatcher,
        action_deps: ActionDeps | None = None,
    ):
        super().__init__()
        self._gamepad = gamepad
        self._index   = 0
        self._action_runner = ActionRunner(
            action_deps,
            lambda q, cb: ConfirmDialog(
                question=q,
                on_confirmed=cb,
                on_cancelled=lambda: None,
                gamepad=self._gamepad,
            ),
        ) if action_deps is not None else None
        self._items:     list[MenuItem]    = []
        self._buttons:   list[QPushButton] = []
        self._on_cancel  = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Standalone layer-shell surface: full-screen backdrop (anchored to all
        # edges) in the overlay layer, so it covers even fullscreen games.
        # keyboard=ON_DEMAND — gamepad (evdev) drives navigation regardless of
        # Wayland focus, so we stay unobtrusive to whatever is underneath.
        make_layer_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.ON_DEMAND,
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch()

        self._card = QWidget()
        self._card.setFixedWidth(500)
        self._card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._card.setStyleSheet(
            "background-color: #1e2430;"
            "border-top-left-radius: 14px;"
            "border-bottom-left-radius: 14px;"
        )

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(32, 32, 32, 32)
        self._card_layout.setSpacing(8)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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

        styles.apply_card_shadow(self._card, offset_x=-10, offset_y=0, blur=50, alpha=220)

        outer.addWidget(self._card)

    # ── Background ─────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        # Translucent dim over the live screen showing through the layer surface
        # — light enough to still see the game/desktop behind the sidebar.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 130))

    # ── Public API ─────────────────────────────────────────────────────────

    def show_overlay(
        self,
        items: list[MenuItem] | None = None,
        on_cancel=None,
    ) -> None:
        """
        Show overlay with a dynamic menu.

        items — list of MenuItem; the static system menu is used when omitted.
        on_cancel — callback invoked when the overlay is dismissed.
        """
        if self.isVisible():
            return
        self._on_cancel = on_cancel
        self._rebuild_buttons(items or [])
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
        self.closed.emit()

    def _dismiss(self) -> None:
        """Close the overlay and restore the previous context (on_cancel)."""
        sound_player.play("popup_close")
        self.hide_overlay()
        if self._on_cancel:
            self._on_cancel()

    # ── Building menu ──────────────────────────────────────────────────────

    def _rebuild_buttons(self, items: list[MenuItem]) -> None:
        while self._buttons_layout.count():
            item = self._buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

        self._items = list(items) if items else self.static_items()

        def _bind_hover(btn: QPushButton, idx: int) -> None:
            def _enter(event) -> None:
                QPushButton.enterEvent(btn, event)
                self._on_hover(idx)
            btn.enterEvent = _enter

        for i, item in enumerate(self._items):
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
            btn.clicked.connect(lambda checked=False, idx=i: self._activate(idx))
            _bind_hover(btn, i)
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

        self.hide_overlay()
        if self._action_runner is not None:
            self._action_runner.run(action)

    # ── Style ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if not self._card.geometry().contains(event.pos()):
            self._dismiss()
        else:
            super().mousePressEvent(event)

    def _on_hover(self, idx: int) -> None:
        if self._index != idx:
            self._index = idx
            self._refresh_buttons()
            sound_player.play("cursor")

    def _refresh_buttons(self) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                styles.home_menu_item_selected() if i == self._index
                else styles.home_menu_item_normal()
            )
