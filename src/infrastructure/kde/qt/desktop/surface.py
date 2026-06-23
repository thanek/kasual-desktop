"""KDE/Wayland Desktop surface — promote the Desktop widget to a layer-shell
TOP-layer surface so it sits above normal and fullscreen windows.

The platform-neutral port (:class:`DesktopSurface`) and the plain fallback live in
``infrastructure.common.qt.desktop.surface``; this is the KDE adapter the Linux
composition root injects.
"""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from infrastructure.kde.qt.ui.layer_shell import (
    Anchor, Keyboard, Layer, make_layer_surface,
)


class LayerShellSurface:
    """The widget is its own frameless top-level window, promoted to a
    wlr-layer-shell TOP-layer surface on Wayland.

    Off Wayland (X11, offscreen tests) :func:`make_layer_surface` is a safe no-op,
    leaving an ordinary frameless top-level window.
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
