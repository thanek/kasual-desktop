import logging
from typing import Callable, _ProtocolMeta  # type: ignore[attr-defined]

import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QLabel, QSizePolicy,
)

from domain.shared.event_emitter import Unsubscribe
from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.menu.cursor import MenuCursor
from domain.menu.item import MenuItem
from domain.shared.feedback import Cue, Feedback
from domain.shell.overlay import HomeMenuOverlay
from infrastructure.common.qt.ui import styles
from infrastructure.common.qt.ui.layer_shell import Layer, Anchor, Keyboard
from infrastructure.common.qt.ui.top_surface import promote_overlay_surface

logger = logging.getLogger(__name__)


class _Meta(type(QWidget), _ProtocolMeta): pass


class HomeOverlay(QWidget, HomeMenuOverlay, metaclass=_Meta):
    """
    Full-screen menu overlay shown when BTN_MODE is pressed.

    A standalone wlr-layer-shell surface in the `overlay` layer, so it sits
    above everything — the KD Desktop, normal windows, and fullscreen games —
    without touching what is underneath. Its translucent backdrop lets the live
    screen show through; the menu card is anchored to the right edge (sidebar).

    Pure presentation: it renders the domain-composed `MenuItem`s, navigates
    them, and reports activation through `on_select(item)`; deciding what each
    item *does* is the controller's job.

    Usage:
        overlay = HomeOverlay(gamepad, feedback)
        overlay.show_overlay(items=[...], on_select=..., on_cancel=...)
        overlay.hide_overlay()
    """

    closed = pyqtSignal()   # emitted when the overlay is dismissed

    def __init__(self, gamepad: PadControl, feedback: Feedback):
        super().__init__()
        self._gamepad = gamepad
        self._feedback = feedback
        # Vertical menu navigation (index + move/select/dismiss) lives in the
        # domain; this widget owns only presentation. wrap=True — the home menu
        # wraps around its ends.
        self._cursor = MenuCursor(
            count=lambda: len(self._items),
            render=self._render_selection,
            on_activate=self._activate,
            on_dismiss=self._dismiss,
            feedback=feedback,
            wrap=True,
        )
        self._items:     list[MenuItem]    = []
        self._buttons:   list[QPushButton] = []
        self._on_select: Callable[[MenuItem], None] | None = None
        self._on_cancel  = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        # Standalone layer-shell surface: full-screen backdrop (anchored to all
        # edges) in the overlay layer, so it covers even fullscreen games.
        # keyboard=NONE — taking any keyboard interactivity makes the compositor
        # deactivate the fullscreen app underneath, which prompts KWin to reveal
        # the panels it hides under fullscreen windows. Navigation is gamepad-
        # driven (evdev) and independent of Wayland focus, so we don't need it.
        promote_overlay_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.NONE,
        )

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = styles.make_card(500)
        # Hug content vertically (Maximum), like the Confirm/Volume dialogs,
        # instead of the old full-height right sidebar.
        self._card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)

        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(32, 32, 32, 32)
        self._card_layout.setSpacing(8)
        self._card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(self.tr("Kasual Desktop"))
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

        outer.addWidget(self._card)

    # ── Public API ─────────────────────────────────────────────────────────

    def show_overlay(
        self,
        items: list[MenuItem],
        on_select: Callable[[MenuItem], None] | None = None,
        on_cancel=None,
    ) -> None:
        """
        Show the overlay with a domain-composed menu.

        items — the `MenuItem`s to render (already localized).
        on_select — invoked with the chosen item when one is activated.
        on_cancel — invoked when the overlay is dismissed (B / backdrop).
        """
        if self.isVisible():
            return
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._rebuild_buttons(items)
        self._cursor.reset(0)
        self._gamepad.push_handler(self._handle_pad)
        self._feedback.play(Cue.POPUP_OPEN)
        self.showFullScreen()
        self.raise_()
        # Deliberately NOT activateWindow(): grabbing Wayland activation would
        # deactivate the fullscreen app underneath, prompting KWin to reveal the
        # panels it hides under fullscreen windows. Navigation is gamepad-driven
        # (evdev), so we don't need focus; keyboard nav still works on demand
        # once the surface is clicked.

    def hide_overlay(self) -> None:
        if not self.isVisible():
            return
        self._gamepad.pop_handler(self._handle_pad)
        self.hide()
        self.closed.emit()

    # ── HomeMenuOverlay port (Qt lifecycle behind a framework-agnostic API) ──

    def is_showing(self) -> bool:
        return self.isVisible()

    def on_closed(self, handler: Callable[[], None]) -> Unsubscribe:
        self.closed.connect(handler)
        return Unsubscribe(lambda: self.closed.disconnect(handler))

    def dispose(self) -> None:
        self.deleteLater()

    def _dismiss(self) -> None:
        """Close the overlay and restore the previous context (on_cancel)."""
        self._feedback.play(Cue.POPUP_CLOSE)
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

        self._items = list(items)

        def _bind_hover(btn: QPushButton, idx: int) -> None:
            def _enter(event) -> None:
                QPushButton.enterEvent(btn, event)
                self._on_hover(idx)
            btn.enterEvent = _enter

        for i, item in enumerate(self._items):
            btn = QPushButton("  " + item.label)
            btn.setMinimumHeight(62)
            if item.icon:
                btn.setIcon(qta.icon(item.icon, color="white"))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked=False, idx=i: self._activate(idx))
            _bind_hover(btn, i)
            self._buttons_layout.addWidget(btn)
            self._buttons.append(btn)

    # ── Selection (delegated to the domain cursor) ───────────────────────────

    @property
    def _index(self) -> int:
        return self._cursor.index

    @_index.setter
    def _index(self, value: int) -> None:
        self._cursor.index = value

    def _handle_pad(self, event: str) -> None:
        self._cursor.handle_pad(event)

    # ── Keyboard ───────────────────────────────────────────────────────────

    _KEY_MAP = {
        Qt.Key.Key_Up:     Event.UP,
        Qt.Key.Key_Down:   Event.DOWN,
        Qt.Key.Key_Return: Event.SELECT,
        Qt.Key.Key_Enter:  Event.SELECT,
        Qt.Key.Key_Escape: Event.CANCEL,
        Qt.Key.Key_F1:     Event.CANCEL,
    }

    def keyPressEvent(self, event: QKeyEvent) -> None:
        mapped = self._KEY_MAP.get(event.key())
        if mapped is not None:
            self._cursor.handle_pad(mapped)

    # ── Actions ────────────────────────────────────────────────────────────

    def _activate(self, idx: int) -> None:
        item = self._items[idx]
        self._feedback.play(Cue.SELECT)
        self.hide_overlay()
        if self._on_select is not None:
            self._on_select(item)

    # ── Style ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if not self._card.geometry().contains(event.pos()):
            self._dismiss()
        else:
            super().mousePressEvent(event)

    def _on_hover(self, idx: int) -> None:
        self._cursor.hover(idx)

    def _render_selection(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setStyleSheet(
                styles.home_menu_item_selected() if i == index
                else styles.home_menu_item_normal()
            )


class HomeOverlayFactory:
    """Builds Home Overlays bound to the gamepad and feedback (OverlayFactory port).

    Holds the `PadControl` and `Feedback` so the controller can create a fresh
    overlay per BTN_MODE press without knowing the widget or its wiring.
    """

    def __init__(self, gamepad: PadControl, feedback: Feedback) -> None:
        self._gamepad = gamepad
        self._feedback = feedback

    def create_home_overlay(self) -> HomeMenuOverlay:
        return HomeOverlay(self._gamepad, self._feedback)
