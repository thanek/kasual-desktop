"""Promote a top-level overlay widget to an always-on-top surface, per platform.

Overlays (ConfirmDialog, the tile popover, Volume/Brightness/…, the Home Overlay)
are standalone top-level windows that must sit above the Desktop, normal windows,
and fullscreen apps. *How* a window achieves that differs by windowing system:

  - Wayland/KWin → a wlr-layer-shell OVERLAY-layer surface (above everything);
  - Windows      → the WS_EX_TOPMOST extended style, which lifts the window above
                   the (non-topmost) foreground app once it is shown;
  - X11/offscreen → left as an ordinary top-level window (the pre-existing fallback).

This is the overlay counterpart of the Desktop's ``DesktopSurface`` seam, keeping
the overlays themselves shared across platforms.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from .layer_shell import Anchor, Keyboard, Layer, make_layer_surface

logger = logging.getLogger(__name__)


def promote_overlay_surface(
    widget: QWidget,
    *,
    layer: Layer = Layer.OVERLAY,
    anchors: Anchor = Anchor.ALL,
    exclusive_zone: int = -1,
    keyboard: Keyboard = Keyboard.NONE,
) -> None:
    """Lift *widget* above everything using the platform's mechanism. Call before
    the widget is shown."""
    platform = QGuiApplication.platformName()
    if platform == "wayland":
        make_layer_surface(
            widget, layer=layer, anchors=anchors,
            exclusive_zone=exclusive_zone, keyboard=keyboard,
        )
    elif platform.startswith("windows"):
        # Qt-managed WS_EX_TOPMOST: set via the window flag rather than raw
        # SetWindowLong, which Qt resets when it shows the window. Added to the
        # existing flags (the overlay is already FramelessWindowHint).
        widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    # else: X11 / offscreen — leave as an ordinary top-level window (unchanged).
