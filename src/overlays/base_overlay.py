"""Base class for fullscreen overlays managed by GamepadWatcher."""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from input.gamepad_watcher import GamepadWatcher


class BaseOverlay(QWidget):
    """
    Base class for fullscreen overlays (ConfirmDialog, VolumeOverlay, etc.).

    Manages:
      - window flags (FramelessWindowHint, WindowStaysOnTopHint, Tool)
      - gamepad lifetime cycle (push/pop_handler)
      - pause() / resume() methods used by Desktop

    Subclass should:
      1. Call super().__init__(gamepad, self._handle_pad, parent)
      2. Build the UI
      3. At the end of __init__ call self._show() (optionally play a sound before that)
    """

    def __init__(
        self,
        gamepad: GamepadWatcher,
        handler: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._gamepad = gamepad
        self._handler = handler
        self._closed  = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150);")

    def _show(self) -> None:
        """Registers the gamepad handler and displays the overlay fullscreen."""
        self._gamepad.push_handler(self._handler)
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def pause(self) -> None:
        """Temporarily hides the overlay (e.g. when Desktop is being minimized)."""
        if not self._closed:
            self._gamepad.pop_handler(self._handler)
            self.hide()

    def resume(self) -> None:
        """Restores the overlay after a pause."""
        if not self._closed:
            self._show()
