"""
Testy jednostkowe dla BrightnessOverlay.

Analogiczne do test_volume_overlay: inicjalizacja z BrightnessControl.get(),
zmiana jasności (krok, zaciski przy MIN/100), aktualizacja labela i slidera,
zamknięcie i rejestracja/wyrejestrowanie handlera pada.

BrightnessControl jest wstrzykiwany jako mock — testy nie dotykają backendu.
"""

from unittest.mock import MagicMock

from domain.system.brightness import Brightness


def _make_overlay(mock_gamepad, brightness=70):
    from infrastructure.qt.overlays.brightness_overlay import BrightnessOverlay
    control = MagicMock()
    control.get.return_value = Brightness(brightness)
    return BrightnessOverlay(gamepad=mock_gamepad, brightness=control, feedback=MagicMock())


class TestInit:
    def test_brightness_read_from_system(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=73)
        assert overlay._brightness.value == 73

    def test_slider_initialized(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=65)
        assert overlay._slider.value() == 65

    def test_label_initialized(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=42)
        assert overlay._value_lbl.text() == "42%"

    def test_registers_handler(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._stack


class TestBrightnessChange:
    def test_right_increases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=50)
        overlay._handle_pad("right")
        assert overlay._brightness.value == 60

    def test_left_decreases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=50)
        overlay._handle_pad("left")
        assert overlay._brightness.value == 40

    def test_clamped_at_max(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=95)
        overlay._handle_pad("right")
        assert overlay._brightness.value == 100

    def test_clamped_at_minimum(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=Brightness.MIN + 2)
        overlay._handle_pad("left")
        assert overlay._brightness.value == Brightness.MIN

    def test_set_called_on_control(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, brightness=50)
        overlay._change(10)
        overlay._control.set.assert_called_once_with(Brightness(60))


class TestClose:
    def test_select_hides_overlay(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_closed_signal_emitted(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        fired = []
        overlay.closed.connect(lambda: fired.append(True))
        overlay._handle_pad("cancel")
        assert fired == [True]

    def test_deregisters_handler_on_close(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("close")
        assert overlay._handle_pad not in mock_gamepad._stack
