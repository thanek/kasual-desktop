"""Tests for the PactlVolumeControl adapter (pactl)."""

from unittest.mock import patch

from system.volume import PactlVolumeControl


class TestGet:
    def test_parses_percent(self):
        out = "Volume: front-left: 52428 / 80% / -5.81 dB,   front-right: 52428 / 80%"
        with patch("system.volume.subprocess.check_output", return_value=out):
            assert PactlVolumeControl().get() == 80

    def test_default_on_error(self):
        with patch("system.volume.subprocess.check_output", side_effect=FileNotFoundError):
            assert PactlVolumeControl().get() == 50


class TestSet:
    def test_calls_pactl_with_percent(self):
        with patch("system.volume.subprocess.Popen") as popen:
            PactlVolumeControl().set(70)
        argv = popen.call_args[0][0]
        assert argv[:3] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@"]
        assert argv[3] == "70%"

    def test_clamps_above_100(self):
        with patch("system.volume.subprocess.Popen") as popen:
            PactlVolumeControl().set(150)
        assert popen.call_args[0][0][3] == "100%"

    def test_clamps_below_0(self):
        with patch("system.volume.subprocess.Popen") as popen:
            PactlVolumeControl().set(-5)
        assert popen.call_args[0][0][3] == "0%"

    def test_swallows_errors(self):
        with patch("system.volume.subprocess.Popen", side_effect=OSError):
            PactlVolumeControl().set(50)   # must not raise
