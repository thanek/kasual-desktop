"""Base class for full-screen layer-shell overlays managed by GamepadWatcher."""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from input.gamepad_watcher import GamepadWatcher
from ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard


class BaseOverlay(QWidget):
    """
    Base class for modal overlays (ConfirmDialog, VolumeOverlay, InfoDialog).

    Each is a standalone wlr-layer-shell surface in the `overlay` layer, so it
    sits above the KD Desktop, normal windows, and fullscreen games. The
    translucent backdrop dims whatever shows through; subclasses add a centered
    card on top.

    Manages the gamepad lifetime (push/pop_handler) and pause()/resume() used
    by Desktop.

    Subclass should:
      1. Call super().__init__(gamepad, self._handle_pad)
      2. Build the UI
      3. Call self._show() at the end of __init__ (optionally after a sound)
    """

    def __init__(
        self,
        gamepad: GamepadWatcher,
        handler: Callable[[str], None],
        parent: QWidget | None = None,   # accepted for API compat; always top-level
    ) -> None:
        super().__init__()
        self._gamepad = gamepad
        self._handler = handler
        self._closed  = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Kasual Overlay")
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        # Standalone layer-shell surface above everything (incl. fullscreen games).
        # keyboard=NONE — taking keyboard interactivity deactivates the fullscreen
        # app underneath, which makes KWin reveal the panels it hides under
        # fullscreen windows. These overlays are gamepad-driven (evdev), so they
        # don't need Wayland focus.
        make_layer_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.NONE,
        )

    def _show(self) -> None:
        """Register the gamepad handler and display the overlay."""
        self._gamepad.push_handler(self._handler)
        self.showFullScreen()
        self.raise_()
        # No activateWindow()/setFocus(): see make_layer_surface above — grabbing
        # Wayland activation would uncover the DE panels behind a fullscreen app.

    def pause(self) -> None:
        """Temporarily hide the overlay (e.g. when the Desktop is minimized)."""
        if not self._closed:
            self._gamepad.pop_handler(self._handler)
            self.hide()

    def resume(self) -> None:
        """Restore the overlay after a pause."""
        if not self._closed:
            self._show()
