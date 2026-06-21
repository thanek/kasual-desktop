"""Surface strategy for the Desktop widget — how its fullscreen, always-on-top
surface is established and driven, per windowing system.

The Desktop QWidget itself is platform-neutral; the *only* part that differs by
OS is how it becomes (and is driven as) a fullscreen, stay-on-top surface:

  - Wayland/KWin → the widget is its own frameless top-level window, promoted to
    a wlr-layer-shell TOP-layer surface (:class:`LayerShellSurface`, the default);
  - Windows → there is no layer-shell, so the widget is hosted inside a separate
    WS_EX_TOPMOST window and shown/hidden through it (see the Windows infra's
    ``WindowsHostSurface``).

Capturing that one difference behind a small port lets the rest of the UI
(TopBar, TileBar, overlays, the whole Desktop widget) stay shared across both
platforms instead of being forked.
"""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from infrastructure.qt.ui.layer_shell import Anchor, Keyboard, Layer, make_layer_surface


@runtime_checkable
class DesktopSurface(Protocol):
    """How the Desktop widget becomes — and is driven as — a fullscreen surface."""

    def install(self, widget: QWidget) -> None:
        """Establish the surface for *widget*. Called once during ``Desktop.__init__``,
        before the widget is ever shown."""

    def show_fullscreen(self) -> None: ...
    def hide(self) -> None: ...
    def activate(self) -> None: ...
    def is_visible(self) -> bool: ...

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        """Register the callback the surface invokes when the platform decides the
        Desktop should return to the foreground (e.g. the app it ceded focus to has
        closed). A no-op where the widget already handles this itself (Linux drives
        it from ``changeEvent``/ActivationChange)."""


class LayerShellSurface:
    """Default surface: the widget is its own frameless top-level window, promoted
    to a wlr-layer-shell TOP-layer surface on Wayland.

    Off Wayland (X11, offscreen tests) :func:`make_layer_surface` is a safe no-op,
    leaving an ordinary frameless top-level window — unchanged from the original
    inline behaviour.
    """

    def __init__(self) -> None:
        self._widget: QWidget | None = None

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        widget.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        make_layer_surface(
            widget,
            layer=Layer.TOP,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.ON_DEMAND,
        )

    def show_fullscreen(self) -> None:
        self._widget.showFullScreen()

    def hide(self) -> None:
        self._widget.hide()

    def activate(self) -> None:
        self._widget.activateWindow()

    def is_visible(self) -> bool:
        return self._widget.isVisible()

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        # Linux drives reactivation from the widget's changeEvent (ActivationChange
        # → on_focus_gained), so there is nothing to wire here.
        pass
