"""How a top-level's hide reaches its Wayland surface.

Mutter: a surface remapped within Qt's 100 ms frame-callback timeout comes up
blank, and the chrome hides and re-shows in one event-loop turn — so the unmap
waits, and a show cancels it. Measured: 100 ms blank, 200 ms renders.

cosmic-comp: an unmap drops the connection, so the surface is parked off-screen
instead and never unmapped — nor, therefore, deleted.
"""

from PyQt6.QtCore import QCoreApplication, QSize, QTimer
from PyQt6.QtGui import QGuiApplication, QHideEvent, QShowEvent
from PyQt6.QtWidgets import QWidget

from infrastructure.common.qt.ui.layer_shell import Anchor
from infrastructure.common.qt.ui.top_surface import (
    surface_sized_by_compositor, unmap_drops_the_connection,
)

UNMAP_DELAY_MS = 150

# Retired parked widgets, held for the process's lifetime: dropping the last
# reference deletes the widget, and deleting tears the surface down.
_kept_alive: list[QWidget] = []


def _layer_shell():
    """The Wayland bindings, reached on use — this package is shared with Windows."""
    from infrastructure.linux.wayland import layer_shell
    return layer_shell


def _mutter_frame_callback_race() -> bool:
    if QGuiApplication.platformName() != "wayland":
        return False
    return not surface_sized_by_compositor()


class _ParkedSurface:
    """A layer surface shrunk to a corner pixel instead of unmapped: off the screen
    with nothing torn down. Qt still calls the widget visible, so the map-state
    events its onlookers filter for are sent by hand."""

    def __init__(self, widget: QWidget, anchors: Anchor) -> None:
        self._widget = widget
        self._anchors = anchors
        self._size_before_parking: QSize | None = None

    @property
    def is_parked(self) -> bool:
        return self._size_before_parking is not None

    def park(self) -> None:
        if self.is_parked:
            return
        layer_shell = _layer_shell()
        self._size_before_parking = self._widget.size()
        layer_shell.set_anchors(self._widget, Anchor.TOP | Anchor.LEFT)
        layer_shell.set_size(self._widget, 1, 1)
        self._commit_with_the_next_frame()
        QCoreApplication.sendEvent(self._widget, QHideEvent())

    def unpark(self) -> None:
        if not self.is_parked:
            return
        # The compositor sizes an anchored surface, so only this undoes the park.
        layer_shell = _layer_shell()
        self._widget.resize(self._size_before_parking)
        self._size_before_parking = None
        layer_shell.set_size(self._widget, 0, 0)
        layer_shell.set_anchors(self._widget, self._anchors)
        self._commit_with_the_next_frame()
        QCoreApplication.sendEvent(self._widget, QShowEvent())

    def _commit_with_the_next_frame(self) -> None:
        self._widget.update()


class SurfaceHiding:
    """Turns a widget's ``hide()`` into whatever this compositor survives."""

    def __init__(self, widget: QWidget, anchors: Anchor = Anchor.ALL) -> None:
        self._widget = widget
        self._deferred = _mutter_frame_callback_race()
        self._parked = (_ParkedSurface(widget, anchors)
                        if unmap_drops_the_connection() else None)
        self._hidden = False
        self._timer = QTimer(widget)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._unmap)

    @property
    def is_hidden(self) -> bool:
        """Whether the last call was a hide. Parked and deferred surfaces stay
        mapped, so Qt's own answer disagrees."""
        return self._hidden

    def hide(self) -> None:
        self._hidden = True
        if self._parked is not None:
            self._parked.park()
        elif not self._deferred:
            self._unmap()
        elif self._widget.isVisible():
            self._timer.start(UNMAP_DELAY_MS)

    def unhide(self) -> None:
        """Undo the hide, whichever form it took. Called as the show begins."""
        self._hidden = False
        self._timer.stop()
        if self._parked is not None:
            self._parked.unpark()

    def retire(self) -> None:
        """Leave the screen for good and give the widget up: deleted, or kept forever
        where deleting would tear its surface down. One never mapped has no surface."""
        mapped = self._widget.isVisible()
        self.hide()
        if self._parked is not None and mapped:
            _kept_alive.append(self._widget)
        else:
            self._widget.deleteLater()

    def _unmap(self) -> None:
        QWidget.hide(self._widget)
