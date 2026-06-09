"""
Testy jednostkowe dla InfoDialog.

InfoDialog dziedziczy zamykanie (_dismiss/force_close) i obsługę kliknięcia
poza kartą z BaseOverlay — te testy domykają ten współdzielony kontrakt:
  - rejestracja/wyrejestrowanie handlera pada
  - select/cancel/close → potwierdzenie + zamknięcie
  - guard podwójnego zamknięcia (_closed)
  - force_close(): zamknięcie bez wywołania callbacku
  - klik poza kartą nie zamyka (InfoDialog ma tylko OK)
"""

from infrastructure.qt.overlays.info_dialog import InfoDialog


def _make_dialog(mock_gamepad, on_confirmed=None):
    return InfoDialog(
        message="Coś się nie udało",
        on_confirmed=on_confirmed or (lambda: None),
        gamepad=mock_gamepad,
    )


class TestHandlerRegistration:
    def test_registers_handler_on_init(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        assert dlg._handle_pad in mock_gamepad._stack

    def test_deregisters_handler_after_confirm(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("select")
        assert dlg._handle_pad not in mock_gamepad._stack


class TestConfirm:
    def test_select_calls_on_confirmed(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("select")
        assert called == [True]

    def test_cancel_also_confirms(self, mock_gamepad):
        # The single-button dialog treats every pad action as acknowledgement.
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("cancel")
        assert called == [True]

    def test_close_also_confirms(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("close")
        assert called == [True]


class TestDoubleCloseGuard:
    def test_callback_called_only_once(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg._handle_pad("select")
        dlg._handle_pad("select")   # _closed=True → noop
        assert called == [True]

    def test_closed_flag_set_after_close(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg._handle_pad("select")
        assert dlg._closed is True


class TestForceClose:
    def test_sets_closed_and_deregisters(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg.force_close()
        assert dlg._closed is True
        assert dlg._handle_pad not in mock_gamepad._stack

    def test_does_not_call_callback(self, mock_gamepad):
        called = []
        dlg = _make_dialog(mock_gamepad, on_confirmed=lambda: called.append(True))
        dlg.force_close()
        assert called == []

    def test_idempotent_second_call_does_not_raise(self, mock_gamepad):
        dlg = _make_dialog(mock_gamepad)
        dlg.force_close()
        dlg.force_close()
        assert dlg._closed is True


class TestOutsideClick:
    def test_outside_click_does_not_close(self, mock_gamepad):
        # InfoDialog keeps the default no-op _on_outside_click — only OK closes it.
        dlg = _make_dialog(mock_gamepad)
        dlg._on_outside_click()
        assert dlg._closed is False
