"""Bazowa klasa dla fullscreen overlayów zarządzanych przez GamepadWatcher."""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from input.gamepad_watcher import GamepadWatcher


class BaseOverlay(QWidget):
    """
    Bazowa klasa dla fullscreen overlayów (ConfirmDialog, VolumeOverlay itp.).

    Zarządza:
      - flagami okna (FramelessWindowHint, WindowStaysOnTopHint, Tool)
      - cyklem life-time pada (push/pop_handler)
      - metodami pause() / resume() używanymi przez Desktop

    Podklasa powinna:
      1. Wywołać super().__init__(gamepad, self._handle_pad, parent)
      2. Zbudować UI
      3. Na końcu __init__ wywołać self._show() (opcjonalnie przed tym zagrać dźwięk)
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
        """Rejestruje handler pada i wyświetla overlay na pełnym ekranie."""
        self._gamepad.push_handler(self._handler)
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()

    def pause(self) -> None:
        """Chowa overlay tymczasowo (np. gdy Desktop jest minimalizowany)."""
        if not self._closed:
            self._gamepad.pop_handler(self._handler)
            self.hide()

    def resume(self) -> None:
        """Przywraca overlay po pauzie."""
        if not self._closed:
            self._show()
