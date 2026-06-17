"""Base class for full-screen layer-shell overlays managed by PadControl."""

import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from domain.input.pad_control import PadControl
from domain.shared.feedback import Cue, Feedback
from infrastructure.qt.ui import styles
from infrastructure.qt.ui.layer_shell import make_layer_surface, Layer, Anchor, Keyboard

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
      1. Call super().__init__(gamepad, self._handle_pad, feedback)
      2. Build the UI
      3. Call self._show() at the end of __init__ (optionally after a sound)
    """

    def __init__(
        self,
        gamepad: PadControl,
        handler: Callable[[str], None],
        feedback: Feedback,
        parent: QWidget | None = None,   # accepted for API compat; always top-level
        *,
        keyboard: Keyboard = Keyboard.NONE,
    ) -> None:
        super().__init__()
        self._gamepad = gamepad
        self._handler = handler
        self._feedback = feedback
        self._keyboard = keyboard
        self._closed  = False
        # Set by build_card(); used to detect clicks outside the card.
        self._card: QWidget | None = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Kasual Overlay")
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        # Standalone layer-shell surface above everything (incl. fullscreen games).
        # keyboard defaults to NONE — taking keyboard interactivity deactivates a
        # fullscreen app underneath, which makes KWin reveal the panels it hides
        # under fullscreen windows. Most overlays are gamepad-driven (evdev) and
        # don't need Wayland focus. An overlay shown when nothing is fullscreen
        # (e.g. first-run onboarding) can opt into keyboard input to be navigable
        # by keyboard as well.
        make_layer_surface(
            self,
            layer=Layer.OVERLAY,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=keyboard,
        )

    def _show(self) -> None:
        """Register the gamepad handler and display the overlay."""
        self._gamepad.push_handler(self._handler)
        self.showFullScreen()
        self.raise_()
        # Grab Wayland activation only when this overlay opted into keyboard input
        # (see make_layer_surface above) — otherwise it would uncover the DE
        # panels hidden behind a fullscreen app.
        if self._keyboard != Keyboard.NONE:
            self.activateWindow()
            self.setFocus()

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

    def _dismiss(self, *, sound: Cue | None = None) -> bool:
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
            self._feedback.play(sound)
        self.hide()
        self.deleteLater()
        return True

    def cancel(self) -> None:
        """Close without callbacks, dropping any pending action (group dismiss,
        or when the underlying app vanished).

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
