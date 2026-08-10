"""Wayland Desktop surface — promote the Desktop widget to a wlr-layer-shell
TOP-layer surface so it sits above normal and fullscreen windows.

The platform-neutral port (:class:`DesktopSurface`) and the plain fallback live in
``infrastructure.common.qt.desktop.surface``; this is the Wayland adapter the Linux
composition root injects.
"""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from infrastructure.common.qt.ui.surface_hiding import SurfaceHiding
from infrastructure.linux.wayland.layer_shell import (
    Anchor, Keyboard, Layer, make_layer_surface, set_keyboard, set_layer,
)


class LayerShellSurface:
    """The widget is its own frameless top-level window, promoted to a
    wlr-layer-shell TOP-layer surface on Wayland.

    Ceding the screen to a launched app (``drop_below``) keeps the surface mapped
    and drawn so its return is a repaint, not a remap — no DE flash. How it stays
    out of the app's way depends on the compositor's stacking, chosen at build:

    - KWin stacks a *focused* fullscreen xdg-toplevel above layer-shell TOP, so
      ceding just drops keyboard interactivity and the app covers the surface on
      TOP. While the app hands focus to an ordinary window instead — a launcher, a
      splash — nothing outranks TOP, and ``sink`` drops the surface to BOTTOM until
      the app holds the screen again.
    - wlroots (Hyprland, Sway) keeps layer-shell TOP above every window, so there
      ceding already drops the surface to the BOTTOM layer, under the app (``sink``
      has nothing left to do), and ``show_fullscreen`` restores it to TOP.

    ``is_visible`` is logical — "the Desktop owns input" — not Qt's mapped-state;
    ``is_on_screen`` is the weaker question. ``hide`` (pause / minimize to tray)
    leaves the screen by whichever route the compositor survives.

    Off Wayland (X11, offscreen tests) :func:`make_layer_surface` is a safe no-op,
    leaving an ordinary frameless top-level window; ``drop_below`` then degrades
    to a plain hide.
    """

    def __init__(self, *, cede_to_bottom: bool = False) -> None:
        self._widget: QWidget | None = None
        self._hiding: SurfaceHiding | None = None
        self._layered  = False
        self._in_front = False
        self._sunk     = False
        self._cede_to_bottom = cede_to_bottom

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        widget.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self._layered = make_layer_surface(
            widget,
            layer=Layer.TOP,
            anchors=Anchor.ALL,
            exclusive_zone=-1,
            keyboard=Keyboard.ON_DEMAND,
        )
        self._hiding = SurfaceHiding(widget, Anchor.ALL)

    def show_fullscreen(self) -> None:
        self._hiding.unhide()
        if self._layered:
            # Unconditional: the surface may have been sunk to BOTTOM under a
            # launcher, and a Desktop returning under the app's windows is no return.
            set_layer(self._widget, Layer.TOP)
            set_keyboard(self._widget, Keyboard.ON_DEMAND)
        self._widget.showFullScreen()
        self._widget.update()
        self._in_front = True
        self._sunk     = False

    def hide(self) -> None:
        self._in_front = False
        self._sunk     = False
        self._hiding.hide()

    def drop_below(self) -> None:
        self._in_front = False
        if self._layered and self._widget.isVisible():
            if self._cede_to_bottom:
                set_layer(self._widget, Layer.BOTTOM)
            set_keyboard(self._widget, Keyboard.NONE)
            self._widget.update()
            self._sunk = self._cede_to_bottom
        else:
            self._hiding.hide()
            self._sunk = False

    def sink(self, under_windows: bool) -> None:
        if self._cede_to_bottom or self._in_front:
            return
        if not self._layered or not self._widget.isVisible():
            return
        set_layer(self._widget, Layer.BOTTOM if under_windows else Layer.TOP)
        self._widget.update()
        self._sunk = under_windows

    def activate(self) -> None:
        self._widget.activateWindow()

    def is_visible(self) -> bool:
        return self._in_front and self._widget.isVisible()

    def is_sunk(self) -> bool:
        return self._sunk

    def is_on_screen(self) -> bool:
        return self._widget.isVisible() and not self._hiding.is_hidden

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        pass   # Linux drives reactivation from the widget's changeEvent instead