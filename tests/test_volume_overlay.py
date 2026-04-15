"""
Testy jednostkowe dla VolumeOverlay.

Testujemy:
  - inicjalizacja z _get_volume()
  - zmiana głośności: krok, zaciski (0/100), aktualizacja labela i slidera
  - zamknięcie przez select/cancel/close: emisja sygnału closed
  - rejestracja/wyrejestrowanie handlera pada

_get_volume i _set_volume są zawsze mockowane – testy nie wywołują pactl.
"""

from unittest.mock import patch


def _make_overlay(mock_gamepad, volume=50):
    """Tworzy VolumeOverlay z zamockowanym systemem audio."""
    with patch("overlays.volume_overlay.VolumeOverlay._get_volume", return_value=volume), \
         patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
        from overlays.volume_overlay import VolumeOverlay
        return VolumeOverlay(gamepad=mock_gamepad)


# ── Inicjalizacja ──────────────────────────────────────────────────────────────

class TestInit:
    def test_volume_read_from_system(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=73)
        assert overlay._volume == 73

    def test_slider_initialized_to_volume(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=65)
        assert overlay._slider.value() == 65

    def test_label_initialized_to_volume(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=42)
        assert overlay._value_lbl.text() == "42%"

    def test_registers_handler(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._handlers


# ── Zmiana głośności ───────────────────────────────────────────────────────────

class TestVolumeChange:
    def test_right_increases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._handle_pad("right")
        assert overlay._volume == 55

    def test_left_decreases_by_step(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._handle_pad("left")
        assert overlay._volume == 45

    def test_volume_clamped_at_max(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=98)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._handle_pad("right")
        assert overlay._volume == 100

    def test_volume_clamped_at_min(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=2)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._handle_pad("left")
        assert overlay._volume == 0

    def test_slider_updated_after_change(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._change(10)
        assert overlay._slider.value() == 60

    def test_label_updated_after_change(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._change(-20)
        assert overlay._value_lbl.text() == "30%"

    def test_set_volume_called_with_new_value(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume") as mock_set:
            overlay._change(5)
        mock_set.assert_called_once_with(55)

    def test_multiple_changes_accumulate(self, mock_gamepad):
        overlay = _make_overlay(mock_gamepad, volume=50)
        with patch("overlays.volume_overlay.VolumeOverlay._set_volume"):
            overlay._change(10)
            overlay._change(10)
            overlay._change(-5)
        assert overlay._volume == 65


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
        assert overlay._handle_pad not in mock_gamepad._handlers
