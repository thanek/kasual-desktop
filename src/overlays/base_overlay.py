"""Base class for full-screen layer-shell overlays managed by GamepadWatcher."""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from audio import sound_player
from input.gamepad_watcher import GamepadWatcher
from ui import styles
from ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard

logger = logging.getLogger(__name__)


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
        # Set by build_card(); used to detect clicks outside the card.
        self._card: QWidget | None = None

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

    # ── Card / closing (shared by all centred dialogs) ───────────────────────

    def build_card(self, width: int) -> QWidget:
        """Create the standard centred card and remember it for outside-click
        detection. Subclasses add their own inner layout to the returned widget."""
        self._card = styles.make_card(width)
        return self._card

    def _dismiss(self, *, sound: str | None = None) -> bool:
        """Tear the overlay down once: deregister the pad handler, hide, delete.

        Returns False if it was already closed, so callers can guard one-shot
        side effects (callbacks, signals). Optionally plays a close sound.
        """
        if self._closed:
            return False
        self._closed = True
        logger.info("%s closing", type(self).__name__)
        self._gamepad.pop_handler(self._handler)
        if sound is not None:
            sound_player.play(sound)
        self.hide()
        self.deleteLater()
        return True

    def force_close(self) -> None:
        """Close without callbacks (e.g. when the underlying app vanished).

        Idempotent and tolerant of an already-closed overlay: still ensures the
        widget is hidden and scheduled for deletion."""
        if not self._closed:
            self._closed = True
            self._gamepad.pop_handler(self._handler)
        self.hide()
        self.deleteLater()

    def _on_outside_click(self) -> None:
        """Action when the backdrop (outside the card) is clicked. Default: keep
        the overlay open. Dismissable dialogs override this."""

    def mousePressEvent(self, event) -> None:
        if self._card is not None and not self._card.geometry().contains(event.pos()):
            self._on_outside_click()
        else:
            super().mousePressEvent(event)
