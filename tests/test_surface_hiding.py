"""Tests for how a hide reaches the Wayland surface.

The layer-shell bindings are monkeypatched — no compositor is contacted.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QWidget

from infrastructure.common.qt.ui import surface_hiding
from infrastructure.common.qt.ui.layer_shell import Anchor
from infrastructure.common.qt.ui.surface_hiding import UNMAP_DELAY_MS, SurfaceHiding

_MODULE = "infrastructure.common.qt.ui.surface_hiding"
_BINDINGS = "infrastructure.linux.wayland.layer_shell"


@pytest.fixture
def kept_alive():
    surface_hiding._kept_alive.clear()
    yield surface_hiding._kept_alive
    surface_hiding._kept_alive.clear()


@pytest.fixture
def widget(qapp):
    w = QWidget()
    w.resize(800, 92)
    w.show()
    return w


class MapWatcher(QObject):
    def __init__(self, widget):
        super().__init__()
        self.seen = []
        widget.installEventFilter(self)

    def eventFilter(self, _obj, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self.seen.append(event.type())
        return False


def _hiding(widget, *, racing=False, parking=False,
            anchors=Anchor.TOP | Anchor.LEFT | Anchor.RIGHT) -> SurfaceHiding:
    with patch(f"{_MODULE}._mutter_frame_callback_race", return_value=racing), \
         patch(f"{_MODULE}.unmap_drops_the_connection", return_value=parking):
        return SurfaceHiding(widget, anchors)


class TestWhereTheCompositorOwnsTheSurface:
    def test_hide_unmaps_at_once(self, widget):
        _hiding(widget).hide()
        assert not widget.isVisible()


class TestWhereTheFrameCallbackRaces:
    def test_hide_does_not_unmap_immediately(self, widget):
        _hiding(widget, racing=True).hide()
        assert widget.isVisible()

    def test_the_unmap_lands_after_the_frame_callback_lifetime(self, widget, qtbot):
        # Held: a collected SurfaceHiding leaves the timer bound to a dead handler.
        hiding = _hiding(widget, racing=True)
        hiding.hide()
        qtbot.waitUntil(lambda: not widget.isVisible(), timeout=UNMAP_DELAY_MS + 500)

    def test_a_show_within_the_window_cancels_the_unmap(self, widget, qtbot):
        hiding = _hiding(widget, racing=True)
        hiding.hide()
        hiding.unhide()
        qtbot.wait(UNMAP_DELAY_MS + 50)
        assert widget.isVisible()

    def test_hiding_an_already_hidden_widget_is_inert(self, widget):
        widget.setVisible(False)
        _hiding(widget, racing=True).hide()
        assert not widget.isVisible()


class TestWhereUnmappingCostsTheConnection:
    def _park(self, widget, **kwargs):
        hiding = _hiding(widget, parking=True, **kwargs)
        with patch(f"{_BINDINGS}.set_anchors") as anchors, \
             patch(f"{_BINDINGS}.set_size") as size:
            hiding.hide()
        return hiding, anchors, size

    def test_the_widget_is_never_unmapped(self, widget):
        self._park(widget)
        assert widget.isVisible()

    def test_hiding_shrinks_the_surface_into_a_corner(self, widget):
        _, anchors, size = self._park(widget)
        assert anchors.call_args.args[1] == Anchor.TOP | Anchor.LEFT
        assert size.call_args.args[1:] == (1, 1)

    def test_showing_restores_the_anchors_and_the_size(self, widget):
        hiding, _, _ = self._park(widget)
        with patch(f"{_BINDINGS}.set_anchors") as anchors, \
             patch(f"{_BINDINGS}.set_size") as size:
            hiding.unhide()
        assert anchors.call_args.args[1] == Anchor.TOP | Anchor.LEFT | Anchor.RIGHT
        # 0 hands the axis back to the window's own size, or the pixel would stick.
        assert size.call_args.args[1:] == (0, 0)
        assert widget.size().height() == 92

    def test_the_move_travels_with_a_repaint(self, widget):
        """Double-buffered state: with no frame to carry it the surface never moves."""
        hiding = _hiding(widget, parking=True)
        with patch(f"{_BINDINGS}.set_anchors"), patch(f"{_BINDINGS}.set_size"), \
             patch.object(widget, "update") as repaint:
            hiding.hide()
            assert repaint.called
            repaint.reset_mock()
            hiding.unhide()
            assert repaint.called

    def test_it_reports_itself_hidden_though_qt_disagrees(self, widget):
        hiding, _, _ = self._park(widget)
        assert hiding.is_hidden and widget.isVisible()

    def test_the_map_state_onlookers_read_still_changes(self, widget):
        watcher = MapWatcher(widget)
        hiding, _, _ = self._park(widget)
        assert watcher.seen[-1] == QEvent.Type.Hide
        with patch(f"{_BINDINGS}.set_anchors"), patch(f"{_BINDINGS}.set_size"):
            hiding.unhide()
        assert watcher.seen[-1] == QEvent.Type.Show

    def test_parking_twice_keeps_the_first_size(self, widget):
        hiding, _, _ = self._park(widget)
        widget.resize(800, 1)   # what the compositor's parked configure does
        with patch(f"{_BINDINGS}.set_anchors"), patch(f"{_BINDINGS}.set_size"):
            hiding.hide()
            hiding.unhide()
        assert widget.size().height() == 92


class TestRetiring:
    def _retire(self, widget, *, parking):
        hiding = _hiding(widget, parking=parking)
        with patch(f"{_BINDINGS}.set_anchors"), patch(f"{_BINDINGS}.set_size"), \
             patch.object(type(widget), "deleteLater") as delete:
            hiding.retire()
        return delete

    def test_an_ordinary_widget_is_deleted(self, widget, kept_alive):
        assert self._retire(widget, parking=False).called
        assert kept_alive == []

    def test_a_parked_widget_is_kept_instead(self, widget, kept_alive):
        assert not self._retire(widget, parking=True).called
        assert kept_alive == [widget]

    def test_one_that_was_never_shown_is_deleted_even_there(self, qapp, kept_alive):
        """No surface was ever created, so there is nothing to tear down."""
        assert self._retire(QWidget(), parking=True).called
        assert kept_alive == []
