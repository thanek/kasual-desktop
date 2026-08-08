"""Hold a top-level's Wayland surface alive across a hide/show that is really a
re-show.

Qt destroys the ``wl_surface`` on ``hide()`` with a frame callback still in flight.
A surface recreated before that callback expires — Qt's timeout is 100 ms — inherits
the stale bookkeeping and commits a buffer it never painted into: the compositor is
left with a correctly sized, fully transparent texture that no later repaint mends.
Measured on Mutter: a 100 ms gap comes up blank, a 200 ms gap renders.

Kasual Desktop's chrome hides and re-shows within one event-loop turn as the Desktop 
comes back, so on GNOME the unmap is deferred and cancelled when the show arrives. 
Where the compositor drives the surface (wlr-layer-shell) the hide stays immediate.
"""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

UNMAP_DELAY_MS = 150


def _mutter_frame_callback_race() -> bool:
    from infrastructure.common.qt.ui.top_surface import surface_sized_by_compositor
    from PyQt6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "wayland":
        return False
    return not surface_sized_by_compositor()


class DeferredUnmap:
    """Turns a widget's ``hide()`` into an unmap that a ``show()`` can still cancel."""

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._enabled = _mutter_frame_callback_race()
        self._timer = QTimer(widget)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._unmap)

    def hide(self) -> None:
        if not self._enabled:
            QWidget.hide(self._widget)
        elif self._widget.isVisible():
            self._timer.start(UNMAP_DELAY_MS)

    def cancel(self) -> None:
        self._timer.stop()

    def _unmap(self) -> None:
        QWidget.hide(self._widget)
