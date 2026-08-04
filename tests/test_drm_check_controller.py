"""Tests for DrmCheckController — the DRM setup card hosted by the Desktop.

The gate and the view are mocked; what matters here is the handshake with the
Desktop's overlay registry, not the card itself.
"""

from unittest.mock import MagicMock

import pytest

from infrastructure.common.qt.desktop.drm_check_controller import DrmCheckController


class FakeGate:
    """Mirrors DrmSetupGate.ensure()."""

    def __init__(self, view, card, ready):
        self._view = view
        self._card = card
        self._ready = ready
        self.forced = None

    def ensure(self, on_done, *, force=False):
        self.forced = force
        if self._ready and not force:
            on_done()
            return
        self._view.current = self._card
        self._view.on_done = on_done


class FakeView:
    def __init__(self):
        self.current = None
        self.on_done = None


class Parts:
    def __init__(self, ready):
        self.view = FakeView()
        self.card = object()
        self.gate = FakeGate(self.view, self.card, ready)
        self.overlays = MagicMock()
        self.hint_bar = MagicMock()
        self.restore = MagicMock()
        self.controller = DrmCheckController(
            self.gate, self.view, self.overlays, self.hint_bar, self.restore,
        )


@pytest.fixture
def make():
    return Parts


@pytest.fixture
def parts(make):
    return make(ready=False)


class TestShow:
    def test_opens_the_card_even_on_a_ready_system(self, make):
        p = make(ready=True)
        p.controller.show()
        assert p.gate.forced is True
        p.overlays.register.assert_called_once_with(p.card)

    def test_card_joins_the_overlay_group(self, parts):
        parts.controller.show()
        parts.overlays.register.assert_called_once_with(parts.card)
        parts.hint_bar.show_hints.assert_called_once()

    def test_second_request_is_ignored_while_the_card_is_up(self, parts):
        parts.controller.show()
        parts.controller.show()
        assert parts.overlays.register.call_count == 1

    def test_nothing_happens_without_a_gate(self):
        overlays = MagicMock()
        DrmCheckController(None, None, overlays, MagicMock(), MagicMock()).show()
        overlays.register.assert_not_called()


class TestEnsure:
    def test_an_incomplete_system_gets_the_card(self, parts):
        assert parts.controller.ensure() is True
        assert parts.gate.forced is False
        parts.overlays.register.assert_called_once_with(parts.card)

    def test_a_ready_system_is_left_alone(self, make):
        p = make(ready=True)
        assert p.controller.ensure() is False
        p.overlays.register.assert_not_called()
        p.overlays.forget.assert_not_called()
        p.hint_bar.show_hints.assert_not_called()
        p.restore.assert_not_called()

    def test_the_menu_entry_still_works_afterwards(self, make):
        p = make(ready=True)
        p.controller.ensure()
        p.controller.show()
        p.overlays.register.assert_called_once_with(p.card)


class TestClose:
    def test_continue_forgets_the_card_and_restores_the_hints(self, parts):
        parts.controller.show()
        parts.view.on_done()
        parts.overlays.forget.assert_called_once_with(parts.card)
        parts.restore.assert_called_once_with()

    def test_the_card_can_be_reopened_afterwards(self, parts):
        parts.controller.show()
        parts.view.on_done()
        parts.controller.show()
        assert parts.overlays.register.call_count == 2

    def test_a_dismissed_overlay_group_leaves_no_stale_handle(self, parts):
        parts.controller.show()
        parts.controller.cancel()
        parts.controller.show()
        assert parts.overlays.register.call_count == 2
        parts.overlays.forget.assert_not_called()
