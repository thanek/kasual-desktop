"""
Testy jednostkowe dla VolumeOverlay.

Testujemy:
  - inicjalizacja z VolumeControl.get()
  - zmiana głośności: krok, zaciski (0/100), aktualizacja labela i slidera
  - zamknięcie przez select/cancel/close: emisja sygnału closed
  - rejestracja/wyrejestrowanie handlera pada

VolumeControl jest wstrzykiwany jako mock — testy nie wywołują pactl.
"""

from unittest.mock import MagicMock

from domain.system.volume import Volume


def _make_overlay(mock_gamepad, volume=50):
    """Tworzy VolumeOverlay ze wstrzykniętym, zamockowanym VolumeControl."""
    from infrastructure.qt.overlays.volume_overlay import VolumeOverlay
    control = MagicMock()
    control.get.return_value = Volume(volume)
    return VolumeOverlay(gamepad=mock_gamepad, volume=control, feedback=MagicMock())


# ── Inicjalizacja ──────────────────────────────────────────────────────────────

class TestInit:
    def test_volume_read_from_system(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=73)
        assert overlay._volume.value == 73

    def test_slider_initialized_to_volume(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=65)
        assert overlay._slider.value() == 65

    def test_label_initialized_to_volume(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=42)
        assert overlay._value_lbl.text() == "42%"

    def test_registers_handler(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._stack


# ── Zmiana głośności ───────────────────────────────────────────────────────────

class TestVolumeChange:
    def test_right_increases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._handle_pad("right")
        assert overlay._volume.value == 55

    def test_left_decreases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._handle_pad("left")
        assert overlay._volume.value == 45

    def test_volume_clamped_at_max(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=98)
        overlay._handle_pad("right")
        assert overlay._volume.value == 100

    def test_volume_clamped_at_min(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=2)
        overlay._handle_pad("left")
        assert overlay._volume.value == 0

    def test_slider_updated_after_change(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._change(10)
        assert overlay._slider.value() == 60

    def test_label_updated_after_change(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._change(-20)
        assert overlay._value_lbl.text() == "30%"

    def test_set_called_on_control_with_new_value(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._change(5)
        overlay._control.set.assert_called_once_with(Volume(55))

    def test_multiple_changes_accumulate(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        overlay._change(10)
        overlay._change(10)
        overlay._change(-5)
        assert overlay._volume.value == 65


# ── Zamknięcie ─────────────────────────────────────────────────────────────────

class TestClose:
    def test_select_hides_overlay(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("select")
        assert not overlay.isVisible()

    def test_cancel_hides_overlay(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("cancel")
        assert not overlay.isVisible()

    def test_close_event_hides_overlay(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("close")
        assert not overlay.isVisible()

    def test_closed_signal_emitted_on_close(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        fired = []
        overlay.closed.connect(lambda: fired.append(True))
        overlay._handle_pad("select")
        assert fired == [True]

    def test_deregisters_handler_on_close(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        overlay._handle_pad("cancel")
        assert overlay._handle_pad not in mock_gamepad._stack
