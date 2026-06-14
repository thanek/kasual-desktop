"""Tests for the BrightnessControl adapters and the DE-dependent selector."""

from unittest.mock import patch

from domain.system.brightness import Brightness
from infrastructure.system.brightness import (
    BrightnessctlBrightnessControl,
    KdeBrightnessControl,
    NullBrightnessControl,
    select_brightness_control,
)


class TestBrightnessctlGet:
    def test_parses_percent(self):
        out = "intel_backlight,backlight,512,40%,1000\n"
        with patch("infrastructure.system.brightness.subprocess.check_output", return_value=out):
            assert BrightnessctlBrightnessControl().get().value == 40

    def test_default_on_error(self):
        with patch("infrastructure.system.brightness.subprocess.check_output", side_effect=FileNotFoundError):
            assert BrightnessctlBrightnessControl().get() == Brightness(Brightness.DEFAULT)


class TestBrightnessctlSet:
    def test_calls_brightnessctl_with_percent(self):
        with patch("infrastructure.system.brightness.subprocess.Popen") as popen:
            BrightnessctlBrightnessControl().set(Brightness(60))
        assert popen.call_args[0][0] == ["brightnessctl", "set", "60%"]

    def test_passes_clamped_value(self):
        with patch("infrastructure.system.brightness.subprocess.Popen") as popen:
            BrightnessctlBrightnessControl().set(Brightness(150))  # clamps to 100
        assert popen.call_args[0][0] == ["brightnessctl", "set", "100%"]

    def test_swallows_errors(self):
        with patch("infrastructure.system.brightness.subprocess.Popen", side_effect=OSError):
            BrightnessctlBrightnessControl().set(Brightness(50))  # must not raise


class TestKdeBrightnessControl:
    def test_get_scales_absolute_to_percent(self):
        with patch.object(KdeBrightnessControl, "_call", side_effect=["400", "1000"]):
            assert KdeBrightnessControl().get().value == 40

    def test_get_default_when_max_zero(self):
        with patch.object(KdeBrightnessControl, "_call", side_effect=["0", "0"]):
            assert KdeBrightnessControl().get() == Brightness(Brightness.DEFAULT)

    def test_set_scales_percent_to_absolute(self):
        with patch.object(KdeBrightnessControl, "_call", return_value="1000"), \
             patch("infrastructure.system.brightness.subprocess.Popen") as popen:
            KdeBrightnessControl().set(Brightness(40))
        assert popen.call_args[0][0][-1] == "400"

    def test_uses_given_qdbus_binary(self):
        with patch.object(KdeBrightnessControl, "_call", return_value="1000"), \
             patch("infrastructure.system.brightness.subprocess.Popen") as popen:
            KdeBrightnessControl("qdbus6").set(Brightness(40))
        assert popen.call_args[0][0][0] == "qdbus6"


class TestNullBrightnessControl:
    def test_get_returns_default(self):
        assert NullBrightnessControl().get() == Brightness(Brightness.DEFAULT)

    def test_set_is_noop(self):
        NullBrightnessControl().set(Brightness(20))  # must not raise


class TestSelector:
    def test_prefers_brightnessctl(self):
        with patch("infrastructure.system.brightness.shutil.which", return_value="/usr/bin/brightnessctl"):
            assert isinstance(select_brightness_control(), BrightnessctlBrightnessControl)

    def test_falls_back_to_kde_with_qdbus6(self):
        def which(name):
            return "/usr/bin/qdbus6" if name == "qdbus6" else None
        with patch("infrastructure.system.brightness.shutil.which", side_effect=which):
            adapter = select_brightness_control()
        assert isinstance(adapter, KdeBrightnessControl)
        assert adapter._qdbus == "qdbus6"

    def test_kde_falls_back_to_unsuffixed_qdbus(self):
        def which(name):
            return "/usr/bin/qdbus" if name == "qdbus" else None
        with patch("infrastructure.system.brightness.shutil.which", side_effect=which):
            adapter = select_brightness_control()
        assert isinstance(adapter, KdeBrightnessControl)
        assert adapter._qdbus == "qdbus"

    def test_falls_back_to_null(self):
        with patch("infrastructure.system.brightness.shutil.which", return_value=None):
            assert isinstance(select_brightness_control(), NullBrightnessControl)
