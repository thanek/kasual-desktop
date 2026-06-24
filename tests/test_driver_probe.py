"""Unit tests for driver_probe — ViGEmBus + HidHide driver detection.

Verifies that ``probe_drivers`` correctly reports which kernel drivers are
installed, and that the all-or-nothing ``exclusive`` property follows D4.

The probe's internal ``_probe_vigembus`` / ``_probe_hidhide`` are patched so
no real DLLs or driver handles are touched.

Skipped on non-Windows: the probed modules use ctypes.WinDLL.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.WinDLL", allow_module_level=True)

from infrastructure.windows.input.driver_probe import DriverCapabilities, probe_drivers


class TestDriverCapabilities:
    def test_both_present_is_exclusive(self):
        caps = DriverCapabilities(vigembus=True, hidhide=True)
        assert caps.exclusive is True

    def test_vigem_only_is_not_exclusive(self):
        caps = DriverCapabilities(vigembus=True, hidhide=False)
        assert caps.exclusive is False

    def test_hidhide_only_is_not_exclusive(self):
        caps = DriverCapabilities(vigembus=False, hidhide=True)
        assert caps.exclusive is False

    def test_neither_is_not_exclusive(self):
        caps = DriverCapabilities(vigembus=False, hidhide=False)
        assert caps.exclusive is False

    def test_frozen(self):
        caps = DriverCapabilities(vigembus=True, hidhide=True)
        with pytest.raises(Exception):
            caps.vigembus = False


class TestProbeDrivers:
    def test_both_present_returns_exclusive(self):
        with patch("infrastructure.windows.input.driver_probe._probe_vigembus", return_value=True), \
             patch("infrastructure.windows.input.driver_probe._probe_hidhide", return_value=True):
            caps = probe_drivers()
        assert caps.vigembus is True
        assert caps.hidhide is True
        assert caps.exclusive is True

    def test_vigem_absent_returns_cooperative(self):
        with patch("infrastructure.windows.input.driver_probe._probe_vigembus", return_value=False), \
             patch("infrastructure.windows.input.driver_probe._probe_hidhide", return_value=True):
            caps = probe_drivers()
        assert caps.vigembus is False
        assert caps.exclusive is False

    def test_hidhide_absent_returns_cooperative(self):
        with patch("infrastructure.windows.input.driver_probe._probe_vigembus", return_value=True), \
             patch("infrastructure.windows.input.driver_probe._probe_hidhide", return_value=False):
            caps = probe_drivers()
        assert caps.hidhide is False
        assert caps.exclusive is False

    def test_both_absent_returns_cooperative(self):
        with patch("infrastructure.windows.input.driver_probe._probe_vigembus", return_value=False), \
             patch("infrastructure.windows.input.driver_probe._probe_hidhide", return_value=False):
            caps = probe_drivers()
        assert caps.vigembus is False
        assert caps.hidhide is False
        assert caps.exclusive is False

    def test_probe_vigembus_catches_exception(self):
        """If the ViGEmBus DLL can't be loaded, _probe_vigembus catches the
        exception and returns False (cooperative fallback)."""
        with patch("infrastructure.windows.input.vigembus_writer._load_vigem_dll",
                   side_effect=OSError("no DLL")), \
             patch("infrastructure.windows.input.driver_probe._probe_hidhide", return_value=True):
            caps = probe_drivers()
        assert caps.vigembus is False

    def test_probe_hidhide_catches_exception(self):
        """If HidHideClient construction raises, _probe_hidhide catches it
        and returns False."""
        with patch("infrastructure.windows.input.hidhide.HidHideClient",
                   side_effect=OSError("no driver")), \
             patch("infrastructure.windows.input.driver_probe._probe_vigembus", return_value=True):
            caps = probe_drivers()
        assert caps.hidhide is False
