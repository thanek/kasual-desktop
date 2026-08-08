"""Tests for the Desktop-side controller that reopens a setup card on demand.

Its job is bookkeeping: join the Desktop's overlay group while the card is up,
leave it when the card closes, and stay inert where there is no gate at all.
"""

from unittest.mock import MagicMock

from domain.shell.open_overlays import OpenOverlays
from infrastructure.common.qt.desktop.setup_check_controller import (
    SetupCheckController,
)


class _View:
    def __init__(self):
        self.current = None


class _Gate:
    """Presents whenever asked, so the controller's own guards are what shows."""

    def __init__(self, view, *, ready=False):
        self._view = view
        self._ready = ready
        self.forced = []

    def ensure(self, on_done, *, force=False):
        self.forced.append(force)
        if self._ready and not force:
            on_done()
            return
        self._view.current = MagicMock()
        self.on_done = on_done


def _controller(gate=None, view=None, overlays=None):
    restored = []
    controller = SetupCheckController(
        gate, view, overlays or OpenOverlays(), MagicMock(),
        restore_hints=lambda: restored.append(True),
    )
    return controller, restored


class TestOpening:
    def test_the_card_joins_the_overlay_group(self):
        view = _View()
        overlays = OpenOverlays()
        controller, _ = _controller(_Gate(view), view, overlays)
        controller.show()
        overlays.pause()
        view.current.pause.assert_called_once()

    def test_reopening_on_demand_forces_the_card_up(self):
        """Otherwise a healthy system would answer by showing nothing at all."""
        view = _View()
        gate = _Gate(view, ready=True)
        controller, _ = _controller(gate, view)
        controller.show()
        assert gate.forced == [True]

    def test_a_second_request_does_not_stack_a_second_card(self):
        view = _View()
        controller, _ = _controller(_Gate(view), view)
        controller.show()
        first = view.current
        controller.show()
        assert view.current is first


class TestWithoutAGate:
    def test_nothing_happens_where_the_pad_is_not_read_through_evdev(self):
        """A Windows build reaches the same Desktop with no gate behind it."""
        controller, _ = _controller(gate=None, view=None)
        controller.show()

    def test_a_view_without_a_gate_is_still_inert(self):
        view = _View()
        controller, _ = _controller(gate=None, view=view)
        controller.show()
        assert view.current is None


class TestClosing:
    def test_leaving_the_card_frees_the_group_and_the_hints(self):
        view = _View()
        overlays = OpenOverlays()
        gate = _Gate(view)
        controller, restored = _controller(gate, view, overlays)
        controller.show()
        card = view.current
        gate.on_done()
        overlays.pause()
        card.pause.assert_not_called()
        assert restored == [True]

    def test_it_can_be_opened_again_afterwards(self):
        view = _View()
        gate = _Gate(view)
        controller, _ = _controller(gate, view)
        controller.show()
        gate.on_done()
        controller.show()
        assert len(gate.forced) == 2

    def test_a_group_teardown_leaves_no_stale_card_behind(self):
        """The overlay registry closes the card itself, without the callback."""
        view = _View()
        gate = _Gate(view)
        controller, restored = _controller(gate, view)
        controller.show()
        controller.cancel()
        controller.show()
        assert len(gate.forced) == 2 and restored == []
