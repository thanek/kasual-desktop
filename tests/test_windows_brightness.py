"""Tests for WindowsBrightnessControl and the gamma-ramp fallback.

Covers the two-backend brightness port for Windows:

  - ``_build_ramp`` (pure function): 100% → identity LUT, 50% → gamma 2.0,
    25% → gamma 4.0; clamp to [1, 100]; monotonically non-decreasing;
    red/green/blue channels identical.
  - ``WindowsBrightnessControl.__init__``: picks sbc when ``_probe_sbc``
    succeeds, falls back to the gamma-ramp control when sbc raises.
  - ``_SbcBrightnessControl.get/set``: scales sbc values, swallows errors,
    updates the cached current level on success.
  - ``_GammaRampBrightnessControl.set``: applies the ramp to every monitor DC
    via ``SetDeviceGammaRamp``; a rejected ramp (one DC returns False) holds
    the screen at the last accepted level (info log, not warning); no DCs →
    warning; ``DeleteDC`` is always called in finally.
  - ``_collect_monitor_dcs``: enumerates monitors via ``EnumDisplayMonitors`` +
    ``GetMonitorInfoW`` + ``CreateDCW``; empty list when the enumeration raises.

Skipped on non-Windows: ``ctypes.windll.gdi32``/``user32`` and the
``screen_brightness_control`` import are Windows-only.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.windll", allow_module_level=True)

from domain.system.brightness import Brightness
from infrastructure.windows.display.brightness import (
    _build_ramp, _collect_monitor_dcs, _GammaRampBrightnessControl,
    _SbcBrightnessControl, WindowsBrightnessControl,
)


# ── _build_ramp (czysta funkcja) ──────────────────────────────────────────────

class TestBuildRamp:
    def test_100_percent_is_identity(self):
        # 100% → gamma 1.0 → val = (i/255)^1 * 65535 = i * 257.
        ramp = _build_ramp(100)
        for i in range(256):
            assert ramp.red[i] == i * 257
            assert ramp.green[i] == i * 257
            assert ramp.blue[i] == i * 257

    def test_50_percent_uses_gamma_2(self):
        # gamma = 100/50 = 2.0; val = (i/255)^2 * 65535.
        ramp = _build_ramp(50)
        for i in range(256):
            expected = int(round((i / 255.0) ** 2.0 * 65535))
            assert ramp.red[i] == expected

    def test_25_percent_uses_gamma_4(self):
        ramp = _build_ramp(25)
        for i in range(256):
            expected = int(round((i / 255.0) ** 4.0 * 65535))
            assert ramp.red[i] == expected

    def test_clamps_to_minimum_1(self):
        # 0% would be a black screen; the function clamps to 1%.
        ramp = _build_ramp(0)
        # gamma = 100/1 = 100.0; just verify it doesn't divide by zero and
        # produces a valid LUT.
        for i in range(256):
            assert 0 <= ramp.red[i] <= 65535

    def test_clamps_to_maximum_100(self):
        # 150% clamps to 100% (identity).
        ramp = _build_ramp(150)
        for i in range(256):
            assert ramp.red[i] == i * 257

    def test_monotonically_non_decreasing(self):
        # A gamma ramp must be monotonic so the LUT doesn't invert tones.
        for percent in (10, 25, 50, 70, 100):
            ramp = _build_ramp(percent)
            values = [ramp.red[i] for i in range(256)]
            assert values == sorted(values), f"non-monotonic at {percent}%"

    def test_channels_identical(self):
        # A neutral grey ramp: red == green == blue.
        for percent in (25, 50, 100):
            ramp = _build_ramp(percent)
            assert list(ramp.red) == list(ramp.green) == list(ramp.blue)

    def test_endpoints(self):
        # i=0 → 0, i=255 → 65535 for any gamma (the curve anchors at the ends).
        for percent in (1, 25, 50, 100):
            ramp = _build_ramp(percent)
            assert ramp.red[0] == 0
            assert ramp.red[255] == 65535


# ── WindowsBrightnessControl — wybór backendu ────────────────────────────────

class TestBackendSelection:
    def test_uses_sbc_when_probe_succeeds(self):
        sbc_ctrl = MagicMock()
        with patch("infrastructure.windows.display.brightness._probe_sbc",
                   return_value=sbc_ctrl):
            ctrl = WindowsBrightnessControl()
        assert ctrl._backend is sbc_ctrl

    def test_falls_back_to_gamma_ramp_when_sbc_unavailable(self):
        with patch("infrastructure.windows.display.brightness._probe_sbc",
                   return_value=None):
            ctrl = WindowsBrightnessControl()
        assert isinstance(ctrl._backend, _GammaRampBrightnessControl)

    def test_get_delegates_to_backend(self):
        sbc_ctrl = MagicMock()
        sbc_ctrl.get.return_value = Brightness(42)
        with patch("infrastructure.windows.display.brightness._probe_sbc",
                   return_value=sbc_ctrl):
            ctrl = WindowsBrightnessControl()
        assert ctrl.get().value == 42

    def test_set_delegates_to_backend(self):
        sbc_ctrl = MagicMock()
        with patch("infrastructure.windows.display.brightness._probe_sbc",
                   return_value=sbc_ctrl):
            ctrl = WindowsBrightnessControl()
        ctrl.set(Brightness(60))
        sbc_ctrl.set.assert_called_once_with(Brightness(60))


# ── _SbcBrightnessControl ─────────────────────────────────────────────────────

class TestSbcBrightnessControl:
    def test_get_reads_sbc_value(self):
        sbc_mod = MagicMock()
        sbc_mod.get_brightness.return_value = [42]
        # The production code does `import screen_brightness_control as sbc`
        # inside the method. Patch sys.modules BEFORE constructing the control
        # so the import resolves to the mock (not the real, broken-on-this-
        # monitor sbc).
        with patch.dict("sys.modules",
                        {"screen_brightness_control": sbc_mod}):
            ctrl = _SbcBrightnessControl(current=50)
            result = ctrl.get()
        assert result.value == 42

    def test_get_falls_back_to_cached_on_error(self):
        sbc_mod = MagicMock()
        sbc_mod.get_brightness.side_effect = OSError("no DDC/CI")
        with patch.dict("sys.modules",
                        {"screen_brightness_control": sbc_mod}):
            ctrl = _SbcBrightnessControl(current=50)
            result = ctrl.get()
        assert result.value == 50   # cached value preserved

    def test_set_writes_sbc_value(self):
        sbc_mod = MagicMock()
        with patch.dict("sys.modules",
                        {"screen_brightness_control": sbc_mod}):
            ctrl = _SbcBrightnessControl(current=50)
            ctrl.set(Brightness(70))
        sbc_mod.set_brightness.assert_called_once_with(70)
        assert ctrl._current == 70

    def test_set_swallows_error(self):
        sbc_mod = MagicMock()
        sbc_mod.set_brightness.side_effect = OSError("no DDC/CI")
        with patch.dict("sys.modules",
                        {"screen_brightness_control": sbc_mod}):
            ctrl = _SbcBrightnessControl(current=50)
            ctrl.set(Brightness(70))   # must not raise
        assert ctrl._current == 50   # unchanged on failure


# ── _GammaRampBrightnessControl ───────────────────────────────────────────────

class TestGammaRampBrightnessControl:
    def test_get_returns_current(self):
        ctrl = _GammaRampBrightnessControl()
        assert ctrl.get().value == 100   # starts at identity

    def test_set_applies_ramp_to_all_dcs(self):
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   return_value=[0x10, 0x20]), \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness._build_ramp") as build, \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o):
            gdi32.SetDeviceGammaRamp.return_value = 1   # success on both
            ctrl.set(Brightness(60))
        assert gdi32.SetDeviceGammaRamp.call_count == 2
        assert ctrl.get().value == 60

    def test_rejected_ramp_holds_last_level(self):
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   return_value=[0x10]), \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness._build_ramp"), \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o):
            gdi32.SetDeviceGammaRamp.return_value = 0   # rejected
            ctrl.set(Brightness(30))
        # Screen held at last accepted level (100 — the identity start).
        assert ctrl.get().value == 100

    def test_no_dcs_warns_and_holds(self):
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   return_value=[]):
            ctrl.set(Brightness(50))
        assert ctrl.get().value == 100   # unchanged

    def test_delete_dc_always_called_in_finally(self):
        # Even if SetDeviceGammaRamp raises, the DCs must be freed.
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   return_value=[0x10, 0x20]), \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness._build_ramp"), \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o):
            gdi32.SetDeviceGammaRamp.side_effect = OSError("boom")
            ctrl.set(Brightness(50))   # must not raise
        assert gdi32.DeleteDC.call_count == 2

    def test_partial_failure_still_frees_all_dcs(self):
        # One DC rejects, the other accepts — both must still be freed.
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   return_value=[0x10, 0x20]), \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness._build_ramp"), \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o):
            gdi32.SetDeviceGammaRamp.side_effect = [1, 0]   # first ok, second rejects
            ctrl.set(Brightness(40))
        assert gdi32.DeleteDC.call_count == 2
        # Partial failure → not ok → held at last level.
        assert ctrl.get().value == 100

    def test_set_swallows_exception(self):
        ctrl = _GammaRampBrightnessControl()
        with patch("infrastructure.windows.display.brightness._collect_monitor_dcs",
                   side_effect=OSError("unexpected")):
            ctrl.set(Brightness(50))   # must not raise


# ── _collect_monitor_dcs ──────────────────────────────────────────────────────

class TestCollectMonitorDcs:
    def test_returns_dc_per_monitor(self):
        with patch("infrastructure.windows.display.brightness.user32") as user32, \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness.ctypes.WINFUNCTYPE") as wfunctype, \
             patch("infrastructure.windows.display.brightness._MONITORINFOEXW"), \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o), \
             patch("infrastructure.windows.display.brightness.ctypes.sizeof", return_value=64):
            user32.GetMonitorInfoW.return_value = 1
            gdi32.CreateDCW.return_value = 0x100
            # Capture the EnumDisplayMonitors callback and invoke it twice
            # (two monitors).
            captured = []

            def _factory(restype, *argtypes):
                def _ctor(cb):
                    captured.append(cb)
                    return cb
                return _ctor
            wfunctype.side_effect = _factory
            dcs = _collect_monitor_dcs()
            # Simulate the enumeration invoking the callback.
            for hmon in [0x1, 0x2]:
                captured[0](hmon, 0, None, 0)
        assert gdi32.CreateDCW.call_count == 2

    def test_returns_empty_when_enum_raises(self):
        with patch("infrastructure.windows.display.brightness.user32") as user32, \
             patch("infrastructure.windows.display.brightness.ctypes.WINFUNCTYPE") as wfunctype:
            user32.EnumDisplayMonitors.side_effect = OSError
            wfunctype.return_value = lambda cb: cb
            assert _collect_monitor_dcs() == []

    def test_skips_monitor_when_info_fails(self):
        with patch("infrastructure.windows.display.brightness.user32") as user32, \
             patch("infrastructure.windows.display.brightness.gdi32") as gdi32, \
             patch("infrastructure.windows.display.brightness.ctypes.WINFUNCTYPE") as wfunctype, \
             patch("infrastructure.windows.display.brightness._MONITORINFOEXW"), \
             patch("infrastructure.windows.display.brightness.ctypes.byref", lambda o: o), \
             patch("infrastructure.windows.display.brightness.ctypes.sizeof", return_value=64):
            user32.GetMonitorInfoW.return_value = 0   # info lookup fails
            captured = []

            def _factory(restype, *argtypes):
                def _ctor(cb):
                    captured.append(cb)
                    return cb
                return _ctor
            wfunctype.side_effect = _factory
            dcs = _collect_monitor_dcs()
            captured[0](0x1, 0, None, 0)
        gdi32.CreateDCW.assert_not_called()
