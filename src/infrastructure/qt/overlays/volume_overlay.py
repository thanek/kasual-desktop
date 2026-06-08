import qtawesome as qta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
)

from infrastructure.audio import sound_player
from infrastructure.input.gamepad_watcher import GamepadWatcher
from ports import VolumeControl
from .base_overlay import BaseOverlay

STEP = 5   # % na jeden krok


class VolumeOverlay(BaseOverlay):
    """Fullscreen overlay with a volume slider."""

    closed = pyqtSignal()

    def __init__(self, gamepad: GamepadWatcher, volume: VolumeControl, parent: QWidget | None = None):
        super().__init__(gamepad, self._handle_pad, parent)
        self._control = volume
        self._volume  = self._control.get()

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = self.build_card(500)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(20)

        # Title
        title_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa5s.volume-up", color="white").pixmap(32, 32))
        icon_lbl.setStyleSheet("background: transparent;")
        title = QLabel("Głośność")
        title.setStyleSheet("font-size: 24px; color: white; background: transparent;")
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(self._volume)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px; background: #4c566a; border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #88c0d0; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 24px; height: 24px; margin: -8px 0;
                background: white; border-radius: 12px;
            }
        """)
        layout.addWidget(self._slider)

        # Value
        self._value_lbl = QLabel(f"{self._volume}%")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_lbl.setStyleSheet("font-size: 32px; color: white; background: transparent;")
        layout.addWidget(self._value_lbl)

        hint = QLabel("◄ ► – zmień   A/Enter – zatwierdź   B/Esc – zamknij")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 14px; color: #888; background: transparent;")
        layout.addWidget(hint)

        outer.addWidget(card)

        sound_player.play("popup_open")
        self._show()

    # ── Gamepad handler ────────────────────────────────────────────────────

    def _handle_pad(self, event: str) -> None:
        if event == "left":
            self._change(-STEP)
        elif event == "right":
            self._change(STEP)
        elif event in ("select", "cancel", "close"):
            self._close()

    def _change(self, delta: int) -> None:
        self._volume = max(0, min(100, self._volume + delta))
        self._slider.setValue(self._volume)
        self._value_lbl.setText(f"{self._volume}%")
        self._control.set(self._volume)
        sound_player.play("cursor")

    # ── Keyboard ───────────────────────────────────────────────────────────

    def _on_outside_click(self) -> None:
        self._close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Left:
            self._change(-STEP)
        elif key == Qt.Key.Key_Right:
            self._change(STEP)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._close()

    # ── Closing ────────────────────────────────────────────────────────────

    def _close(self) -> None:
        if self._dismiss(sound="popup_close"):
            self.closed.emit()

