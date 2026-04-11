"""
Testy jednostkowe dla ConfirmDialog.

Testujemy:
  - rejestracja/wyrejestrowanie handlera pada
  - nawigacja padem: select (tak/nie), cancel/close, left/right
  - guard podwójnego zamknięcia (_closed)
  - force_close(): zamknięcie bez wywołania callbacków

Widget jest tworzony w trybie offscreen – showFullScreen() nie wymaga
prawdziwego wyświetlacza.
"""

from confirm_dialog import ConfirmDialog


def _make_dialog(mock_gamepad, on_confirmed=None, on_cancelled=None):
    return ConfirmDialog(
        question="Czy na pewno?",
        on_confirmed=on_confirmed or (lambda: None),
        on_cancelled=on_cancelled or (lambda: None),
        gamepad=mock_gamepad,
    )


# ── Rejestracja handlera ───────────────────────────────────────────────────────

class TestHandlerRegistration:
    def test_registers_handler_on_init(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        assert dlg._handle_pad in mock_gamepad._handlers

    def test_deregisters_handler_after_confirm(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("select")   # _focus_yes=True → potwierdza i zamyka
        assert dlg._handle_pad not in mock_gamepad._handlers

    def test_deregisters_handler_after_cancel(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("cancel")
        assert dlg._handle_pad not in mock_gamepad._handlers


# ── Pad: select ────────────────────────────────────────────────────────────────

class TestPadSelect:
    def test_select_with_focus_yes_calls_on_confirmed(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        assert dlg._focus_yes is True
        dlg._handle_pad("select")
        assert called == [True]

    def test_select_with_focus_no_calls_on_cancelled(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_cancelled=lambda: called.append(True))
        dlg._focus_yes = False
        dlg._handle_pad("select")
        assert called == [True]

    def test_select_does_not_call_both_callbacks(self, mock_gamepad):
        confirmed, cancelled = [], []
        dlg = _make_dialog(
            mock_gamepad,
            on_confirmed=lambda: confirmed.append(True),
            on_cancelled=lambda: cancelled.append(True),
        )
        dlg._handle_pad("select")
        assert len(confirmed) + len(cancelled) == 1


# ── Pad: cancel / close ────────────────────────────────────────────────────────

class TestPadCancelClose:
    def test_cancel_calls_on_cancelled(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_cancelled=lambda: called.append(True))
        dlg._handle_pad("cancel")
        assert called == [True]

    def test_close_calls_on_cancelled(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_cancelled=lambda: called.append(True))
        dlg._handle_pad("close")
        assert called == [True]

    def test_cancel_does_not_call_on_confirmed(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("cancel")
        assert called == []


# ── Pad: left / right ─────────────────────────────────────────────────────────

class TestPadFocusToggle:
    def test_right_toggles_focus_to_no(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        assert dlg._focus_yes is True
        dlg._handle_pad("right")
        assert dlg._focus_yes is False

    def test_left_toggles_focus_to_no(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("left")
        assert dlg._focus_yes is False

    def test_double_toggle_restores_focus(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("left")
        dlg._handle_pad("left")
        assert dlg._focus_yes is True


# ── Guard podwójnego zamknięcia ────────────────────────────────────────────────

class TestDoubleCloseGuard:
    def test_callback_called_only_once(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("select")
        dlg._handle_pad("select")   # drugi raz – _closed=True → noop
        assert called == [True]

    def test_closed_flag_set_after_close(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("cancel")
        assert dlg._closed is True


# ── force_close ────────────────────────────────────────────────────────────────

class TestForceClose:
    def test_sets_closed_flag(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg.force_close()
        assert dlg._closed is True

    def test_deregisters_handler(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg.force_close()
        assert dlg._handle_pad not in mock_gamepad._handlers

    def test_does_not_call_any_callback(self, mock_gamepad):
        confirmed, cancelled = [], []
        dlg = _make_dialog(
            mock_gamepad,
            on_confirmed=lambda: confirmed.append(True),
            on_cancelled=lambda: cancelled.append(True),
        )
        dlg.force_close()
        assert confirmed == [] and cancelled == []

    def test_idempotent_second_call_does_not_raise(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg.force_close()
        dlg.force_close()   # nie powinno rzucać
        assert dlg._closed is True
