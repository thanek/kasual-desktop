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
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from .layer_shell import Anchor, Keyboard, Layer

if TYPE_CHECKING:
    from infrastructure.linux.compositor import Compositor

logger = logging.getLogger(__name__)

HOME_EDGE_MARGIN      = 10
GNOME_PANEL_CLEARANCE = 32


def _wayland_compositor(compositor: "Compositor | None" = None) -> "Compositor | None":
    """The compositor in play, or None when this is not a Wayland session."""
    if QGuiApplication.platformName() != "wayland":
        return None
    if compositor is not None:
        return compositor
    from infrastructure.linux.compositor import detect_compositor
    return detect_compositor()


def _on_gnome(compositor: "Compositor | None" = None) -> bool:
    resolved = _wayland_compositor(compositor)
    if resolved is None:
        return False
    from infrastructure.linux.compositor import Compositor
    return resolved is Compositor.GNOME


def _on_layer_shell(compositor: "Compositor | None" = None) -> bool:
    """Whether this session really puts our overlays on wlr-layer-shell — which
    needs both a compositor that implements it and a loadable Qt6 LayerShellQt."""
    resolved = _wayland_compositor(compositor)
    if resolved is None:
        return False
    from infrastructure.linux.compositor import layer_shell_available
    return layer_shell_available(resolved)


def home_chrome_edge_margin(compositor: "Compositor | None" = None) -> int:
    """The gap the Home header (top) and hint bar (bottom) keep from the screen
    edge — widened on GNOME to clear its unstackable top panel."""
    return GNOME_PANEL_CLEARANCE if _on_gnome(compositor) else HOME_EDGE_MARGIN


def surface_sized_by_compositor(compositor: "Compositor | None" = None) -> bool:
    """Whether the windowing system gives an anchored overlay its geometry.

    wlr-layer-shell sizes a surface from its anchors before it is ever mapped.
    Everywhere else the widget must size itself: a compositor-driven resize after
    the fact leaves the client with a buffer it never repaints — and an overlay
    that is sized by neither side never appears, which is what a Wayland session
    without a usable LayerShellQt would otherwise produce."""
    return _on_layer_shell(compositor)


def fullscreen_loses_translucency(compositor: "Compositor | None" = None) -> bool:
    """Whether a fullscreen surface is composited over opaque black.

    Mutter blends a fullscreen window onto black and drops its alpha channel, so a
    dimming backdrop would hide the screen instead of shading it. A screen-sized
    ordinary window keeps its alpha. Measured: painting rgba(255,0,0,100) fullscreen
    reads back as rgba(100,0,0,255).

    The risk is not Mutter's alone — it is what an *ordinary top-level* asking for
    fullscreen invites anywhere, since a compositor is then free to put it straight
    on the scanout plane with nothing behind it to blend. A layer-shell overlay is
    sized by its anchors and never asks, so it keeps its alpha; wherever layer-shell
    is unavailable the screen-sized window is the safe shape."""
    resolved = _wayland_compositor(compositor)
    return resolved is not None and not _on_layer_shell(resolved)


def promote_overlay_surface(
    widget: QWidget,
    *,
    layer: Layer = Layer.OVERLAY,
    anchors: Anchor = Anchor.ALL,
    exclusive_zone: int = -1,
    keyboard: Keyboard = Keyboard.NONE,
    compositor: "Compositor | None" = None,
) -> None:
    """Lift *widget* above everything using the platform's mechanism. Call before
    the widget is shown."""
    platform = QGuiApplication.platformName()
    if platform == "wayland":
        if _on_gnome(compositor):
            # Mutter has no layer-shell; the Kasual Helper extension pins Kasual's
            # surfaces above the foreground app (a plain frameless top-level here)
            # and applies the layer/anchors/keyboard mode itself, keyed by the window
            # title. Asking for the screen here would take it from the app underneath.
            from infrastructure.gnome.helper import helper_present, set_surface_role
            if helper_present():
                set_surface_role(widget.windowTitle(), layer, anchors, keyboard)
            return
        # The LayerShellQt binding is the Wayland adapter; imported lazily so this
        # shared dispatcher carries no eager dependency on it (the enums above are
        # the platform-neutral vocabulary).
        from infrastructure.linux.wayland.layer_shell import make_layer_surface
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
