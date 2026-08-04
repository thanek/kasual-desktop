"""Tests for DrmCheckController — the menu-opened setup card, over fakes.

The gate and the view are mocked; what matters here is the handshake with the
Desktop's overlay registry, not the card itself.
"""

from unittest.mock import MagicMock

import pytest

from infrastructure.common.qt.desktop.drm_check_controller import DrmCheckController


class FakeGate:
    """Presents through the view the way the real gate does on a forced open."""

    def __init__(self, view, card):
        self._view = view
        self._card = card
        self.forced = None

    def ensure(self, on_done, *, force=False):
        self.forced = force
        self._view.current = self._card
        self._view.on_done = on_done


class FakeView:
    def __init__(self):
        self.current = None
        self.on_done = None


@pytest.fixture
def parts():
    view = FakeView()
    card = object()
    gate = FakeGate(view, card)
    overlays, hint_bar, restore = MagicMock(), MagicMock(), MagicMock()
    controller = DrmCheckController(gate, view, overlays, hint_bar, restore)
    return controller, gate, view, card, overlays, hint_bar, restore


class TestShow:
    def test_opens_the_card_even_on_a_ready_system(self, parts):
        controller, gate, *_ = parts
        controller.show()
        assert gate.forced is True

    def test_card_joins_the_overlay_group(self, parts):
        controller, _, _, card, overlays, hint_bar, _ = parts
        controller.show()
        overlays.register.assert_called_once_with(card)
        hint_bar.show_hints.assert_called_once()

    def test_second_request_is_ignored_while_the_card_is_up(self, parts):
        controller, _, _, _, overlays, *_ = parts
        controller.show()
        controller.show()
        assert overlays.register.call_count == 1

    def test_nothing_happens_without_a_gate(self):
        overlays = MagicMock()
        DrmCheckController(None, None, overlays, MagicMock(), MagicMock()).show()
        overlays.register.assert_not_called()


class TestClose:
    def test_continue_forgets_the_card_and_restores_the_hints(self, parts):
        controller, _, view, card, overlays, _, restore = parts
        controller.show()
        view.on_done()
        overlays.forget.assert_called_once_with(card)
        restore.assert_called_once_with()

    def test_the_card_can_be_reopened_afterwards(self, parts):
        controller, _, view, _, overlays, *_ = parts
        controller.show()
        view.on_done()
        controller.show()
        assert overlays.register.call_count == 2

    def test_a_dismissed_overlay_group_leaves_no_stale_handle(self, parts):
        controller, _, _, _, overlays, *_ = parts
        controller.show()
        controller.cancel()
        controller.show()
        assert overlays.register.call_count == 2
        overlays.forget.assert_not_called()
