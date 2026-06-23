"""Tests for the PactlVolumeControl adapter (pactl)."""

from unittest.mock import patch

from domain.system.volume import Volume
from infrastructure.kde.volume import PactlVolumeControl


class TestGet:
    def test_parses_percent(self):
        out = "Volume: front-left: 52428 / 80% / -5.81 dB,   front-right: 52428 / 80%"
        with patch("infrastructure.kde.volume.subprocess.check_output", return_value=out):
            assert PactlVolumeControl().get().value == 80

    def test_default_on_error(self):
        with patch("infrastructure.kde.volume.subprocess.check_output", side_effect=FileNotFoundError):
            assert PactlVolumeControl().get() == Volume(Volume.DEFAULT)


class TestSet:
    def test_calls_pactl_with_percent(self):
        with patch("infrastructure.kde.volume.subprocess.Popen") as popen:
            PactlVolumeControl().set(Volume(70))
        argv = popen.call_args[0][0]
        assert argv[:3] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@"]
        assert argv[3] == "70%"

    def test_passes_clamped_value_from_volume(self):
        with patch("infrastructure.kde.volume.subprocess.Popen") as popen:
            PactlVolumeControl().set(Volume(150))  # Volume clamps to 100
        assert popen.call_args[0][0][3] == "100%"

    def test_swallows_errors(self):
        with patch("infrastructure.kde.volume.subprocess.Popen", side_effect=OSError):
            PactlVolumeControl().set(Volume(50))   # must not raise
