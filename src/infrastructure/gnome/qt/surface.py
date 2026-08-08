"""GNOME Desktop surface — a frameless fullscreen window kept above everything
by the Kasual Helper extension (Mutter has no wlr-layer-shell).

Mirrors :class:`LayerShellSurface`: the Desktop is its own frameless top-level
window; showing it asks the extension to pin Kasual Desktop's surfaces above 
the foreground app. The app returning to the foreground is driven by the 
domain (``activate_windows_for_pids``), exactly as on the layer-shell path.

Ceding to a launched app (``drop_below``) keeps the Desktop mapped but tells the
extension to stop raising it over the app and let the app scan out; a fullscreen
app covers it, and when that window unmaps the already-drawn Desktop is revealed
with no remap. ``is_visible`` is therefore logical — "the Desktop is in front" —
not Qt's mapped-state. ``hide`` (pause / minimize to tray) still truly unmaps.
"""

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from infrastructure.common.qt.ui.layer_shell import Anchor, Keyboard, Layer
from infrastructure.gnome import helper

_TITLE = "Kasual Desktop"


class GnomeSurface:
    def __init__(self) -> None:
        self._widget: QWidget | None = None
        self._in_front = False

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        widget.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        widget.setWindowTitle(_TITLE)
        # Below the overlays, which register themselves in the OVERLAY layer.
        helper.set_surface_role(_TITLE, Layer.TOP, Anchor.ALL, Keyboard.ON_DEMAND)

    def show_fullscreen(self) -> None:
        # Ask first: Mutter decides to scan a fullscreen window straight out as it
        # maps, and a scanned-out Desktop stops the compositor from drawing Kasual's
        # other surfaces at all.
        helper.show_overlay()
        self._widget.showFullScreen()
        helper.activate_surface(_TITLE)
        self._in_front = True

    def hide(self) -> None:
        self._in_front = False
        # Unmap first: releasing the pin while the Desktop is still mapped would
        # drop it behind the game for a frame.
        self._widget.hide()
        helper.hide_overlay()

    def drop_below(self) -> None:
        self._in_front = False
        # Stay mapped; the extension restacks the Desktop below the app. Only
        # reached for fullscreen apps (which cover it) — others take hide().
        helper.cede_overlay()

    def sink(self, under_windows: bool) -> None:
        # The extension already follows the focus, which tells it what the app is
        # showing before our window list does (it is polled).
        pass

    def activate(self) -> None:
        self._widget.activateWindow()
        helper.activate_surface(_TITLE)

    def is_visible(self) -> bool:
        return self._in_front and self._widget.isVisible()

    def is_sunk(self) -> bool:
        return not self._in_front and self._widget.isVisible() and helper.is_sunk()

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        pass   # Linux drives reactivation from the widget's changeEvent instead
