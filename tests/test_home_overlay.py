"""
Testy jednostkowe dla HomeOverlay (warstwa prezentacji).

Po przeniesieniu składania menu i dispatchu do dziedziny/kontrolera overlay
tylko renderuje listę `MenuItem`, nawiguje po niej i raportuje wybór przez
`on_select` oraz odrzucenie przez `on_cancel`. Zachowania akcji (np. potwierdzenia
akcji systemowych) są testowane przy `ActionRunner` w test_system_actions.py.

Testujemy:
  - show_overlay / hide_overlay: rejestracja handlera, idempotentność
  - budowanie przycisków z przekazanych MenuItem
  - nawigacja padem: up/down (z zawijaniem), cancel/close
  - reset indeksu przy każdym show_overlay
  - _activate: woła on_select z właściwym MenuItem i chowa overlay
  - _dismiss: woła on_cancel
"""

from domain.menu.item import MenuItem


def _items(n: int = 3) -> list[MenuItem]:
    return [MenuItem(label=f"Item {i}", action=f"a{i}", icon="fa5s.home") for i in range(n)]


def _make_overlay(mock_gamepad):
    from infrastructure.qt.overlays.home_overlay import HomeOverlay
    return HomeOverlay(gamepad=mock_gamepad)


def _shown(mock_gamepad, items=None, on_select=None, on_cancel=None):
    """Zwraca overlay w stanie pokazanym (show_overlay wywołane)."""
    overlay = _make_overlay(mock_gamepad)
    overlay.show_overlay(items=items or _items(), on_select=on_select, on_cancel=on_cancel)
    return overlay


# ── show_overlay / hide_overlay ───────────────────────────────────────────────

class TestShowHide:
    def test_show_registers_handler(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._stack
        overlay.hide_overlay()

    def test_hide_deregisters_handler(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        overlay.hide_overlay()
        assert overlay._handle_pad not in mock_gamepad._stack

    def test_double_show_does_not_register_handler_twice(self, mock_gamepad):
        overlay = _shown(mock_gamepad)
        count_before = len(mock_gamepad._stack)
        overlay.show_overlay(items=_items())   # już widoczny – noop
        assert len(mock_gamepad._stack) == count_before
        overlay.hide_overlay()

    def test_hide_when_not_visible_is_noop(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay.hide_overlay()   # nigdy nie pokazywany – nie powinno rzucać


# ── Budowanie pozycji menu ────────────────────────────────────────────────────

class TestItemBuilding:
    def test_buttons_count_matches_items(self, mock_gamepad):
        overlay = _shown(mock_gamepad, items=_items(4))
        assert len(overlay._buttons) == 4
        overlay.hide_overlay()

    def test_items_are_stored(self, mock_gamepad):
        items = _items(2)
        overlay = _shown(mock_gamepad, items=items)
        assert overlay._items == items
        overlay.hide_overlay()

    def test_buttons_rebuilt_on_second_show(self, mock_gamepad):
        overlay = _shown(mock_gamepad, items=_items(3))
        overlay.hide_overlay()
        overlay.show_overlay(items=_items(1))
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
        overlay.show_overlay(items=_items())
        assert overlay._index == 0
        overlay.hide_overlay()


# ── _activate ─────────────────────────────────────────────────────────────────

class TestActivate:
    def test_select_calls_on_select_with_current_item(self, mock_gamepad):
        items = _items(3)
        chosen = []
        overlay = _shown(mock_gamepad, items=items, on_select=chosen.append)
        overlay._index = 2
        overlay._handle_pad("select")
        assert chosen == [items[2]]

    def test_select_hides_overlay(self, mock_gamepad):
        overlay = _shown(mock_gamepad, items=_items(), on_select=lambda item: None)
        overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_select_without_on_select_does_not_raise(self, mock_gamepad):
        overlay = _shown(mock_gamepad)   # on_select=None
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
