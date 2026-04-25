"""
Testy jednostkowe dla HomeOverlay.

Testujemy:
  - show_overlay / hide_overlay: rejestracja handlera, idempotentność
  - budowanie listy pozycji (items vs. _STATIC_ITEMS)
  - nawigacja padem: up/down (z zawijaniem), cancel/close
  - resetowanie indeksu przy każdym show_overlay
  - _activate: wywołanie callbacku, akcja cancel, akcja systemowa
"""

import pytest
from unittest.mock import MagicMock, patch

from overlays.home_overlay import HomeOverlay, MenuItem
from system.system_actions import ActionDeps


def _make_overlay(mock_gamepad, action_deps=None):
    return HomeOverlay(gamepad=mock_gamepad, action_deps=action_deps)


def _shown(mock_gamepad, items=None, on_cancel=None, action_deps=None):
    """Zwraca overlay w stanie pokazanym (show_overlay wywołane)."""
    overlay = _make_overlay(mock_gamepad, action_deps=action_deps)
    overlay.show_overlay(items=items, on_cancel=on_cancel)
    return overlay


# ── show_overlay / hide_overlay ───────────────────────────────────────────────

class TestShowHide:
    def test_show_registers_handler(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._handlers
        overlay.hide_overlay()

    def test_hide_deregisters_handler(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay.hide_overlay()
        assert overlay._handle_pad not in mock_gamepad._handlers

    def test_double_show_does_not_register_handler_twice(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        count_before = len(mock_gamepad._handlers)
        overlay.show_overlay()   # już widoczny – noop
        assert len(mock_gamepad._handlers) == count_before
        overlay.hide_overlay()

    def test_hide_when_not_visible_is_noop(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay.hide_overlay()   # nigdy nie pokazywany – nie powinno rzucać


# ── Budowanie pozycji menu ────────────────────────────────────────────────────

class TestItemBuilding:
    def test_default_items_are_static(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        assert overlay._items == HomeOverlay.static_items()
        overlay.hide_overlay()

    def test_buttons_count_matches_items(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        assert len(overlay._buttons) == len(overlay._items)
        overlay.hide_overlay()

    def test_buttons_rebuilt_on_second_show(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay.hide_overlay()
        items = [MenuItem(label="A", icon="fa5s.times", callback=lambda: None)]
        overlay.show_overlay(items=items)
        assert len(overlay._buttons) == 1
        overlay.hide_overlay()


# ── Nawigacja padem ───────────────────────────────────────────────────────────

class TestNavigation:
    def test_down_increments_index(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._handle_pad("down")
        assert overlay._index == 1
        overlay.hide_overlay()

    def test_up_from_zero_wraps_to_last(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._handle_pad("up")
        assert overlay._index == len(overlay._items) - 1
        overlay.hide_overlay()

    def test_down_from_last_wraps_to_zero(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._index = len(overlay._items) - 1
        overlay._handle_pad("down")
        assert overlay._index == 0
        overlay.hide_overlay()

    def test_cancel_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._handle_pad("cancel")
        assert not overlay.isVisible()

    def test_close_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._handle_pad("close")
        assert not overlay.isVisible()

    def test_index_reset_to_zero_on_each_show(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay._handle_pad("down")
        overlay._handle_pad("down")
        overlay.hide_overlay()
        overlay.show_overlay()
        assert overlay._index == 0
        overlay.hide_overlay()


# ── _activate ─────────────────────────────────────────────────────────────────

class TestActivate:
    def test_callback_item_called_on_select(self, mock_gamepad):
        called = []
        items = [MenuItem(label="X", icon="fa5s.times", callback=lambda: called.append(True))]
        overlay = _shown(mock_gamepad, items=items)
        overlay._handle_pad("select")
        assert called == [True]

    def test_callback_item_hides_overlay(self, mock_gamepad):
        items = [MenuItem(label="A", icon="fa5s.times", callback=lambda: None)]
        overlay = _shown(mock_gamepad, items=items)
        overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_cancel_action_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        cancel_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == "cancel")
        overlay._index = cancel_idx
        overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_cancel_action_calls_on_cancel(self, mock_gamepad):
        called = []
        overlay = _shown(mock_gamepad, on_cancel=lambda: called.append(True))
        cancel_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == "cancel")
        overlay._index = cancel_idx
        overlay._handle_pad("select")
        assert called == [True]

    @pytest.mark.parametrize("action", ["sleep", "restart", "shutdown"])
    def test_system_action_calls_ask_confirmation(self, action, mock_gamepad):
        overlay = _shown(mock_gamepad, action_deps=ActionDeps(desktop=MagicMock()))
        action_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == action)
        overlay._index = action_idx
        with patch("overlays.home_overlay.ConfirmDialog") as mock_dlg:
            overlay._handle_pad("select")
        mock_dlg.assert_called_once()

    @pytest.mark.parametrize("action", ["sleep", "restart", "shutdown"])
    def test_system_action_hides_overlay_before_confirming(self, action, mock_gamepad):
        overlay = _shown(mock_gamepad, action_deps=ActionDeps(desktop=MagicMock()))
        action_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == action)
        overlay._index = action_idx
        with patch("overlays.home_overlay.ConfirmDialog"):
            overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_hide_desktop_calls_pause_immediately(self, mock_gamepad):
        desktop = MagicMock()
        overlay = _shown(mock_gamepad, action_deps=ActionDeps(desktop=desktop))
        hide_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == "hide_desktop")
        overlay._index = hide_idx
        with patch("overlays.home_overlay.ConfirmDialog") as mock_dlg:
            overlay._handle_pad("select")
        mock_dlg.assert_not_called()
        desktop.pause.assert_called_once()

    def test_hide_desktop_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad, action_deps=ActionDeps(desktop=MagicMock()))
        hide_idx = next(i for i, it in enumerate(overlay._items) if it.get("action") == "hide_desktop")
        overlay._index = hide_idx
        overlay._handle_pad("select")
        assert not overlay.isVisible()


# ── _dismiss ──────────────────────────────────────────────────────────────────

class TestDismiss:
    def test_pad_cancel_calls_on_cancel(self, mock_gamepad):
        called = []
        overlay = _shown(mock_gamepad, on_cancel=lambda: called.append(True))
        overlay._handle_pad("cancel")
        assert called == [True]

    def test_pad_close_calls_on_cancel(self, mock_gamepad):
        called = []
        overlay = _shown(mock_gamepad, on_cancel=lambda: called.append(True))
        overlay._handle_pad("close")
        assert called == [True]

    def test_pad_cancel_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad, on_cancel=lambda: None)
        overlay._handle_pad("cancel")
        assert not overlay.isVisible()

    def test_dismiss_without_on_cancel_does_not_raise(self, mock_gamepad):
        overlay = _shown(mock_gamepad)   # on_cancel=None
        overlay._handle_pad("cancel")   # nie powinno rzucać
        assert not overlay.isVisible()
