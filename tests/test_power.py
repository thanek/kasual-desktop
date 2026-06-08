"""Tests for the SystemdPowerControl adapter (systemctl)."""

from unittest.mock import patch

from infrastructure.system.power import SystemdPowerControl


class TestSystemdPowerControl:
    def test_suspend(self):
        with patch("infrastructure.system.power.subprocess.Popen") as popen:
            SystemdPowerControl().suspend()
        popen.assert_called_once_with(["systemctl", "suspend"])

    def test_reboot(self):
        with patch("infrastructure.system.power.subprocess.Popen") as popen:
            SystemdPowerControl().reboot()
        popen.assert_called_once_with(["systemctl", "reboot"])

    def test_poweroff(self):
        with patch("infrastructure.system.power.subprocess.Popen") as popen:
            SystemdPowerControl().poweroff()
        popen.assert_called_once_with(["systemctl", "poweroff"])

    def test_swallows_errors(self):
        with patch("infrastructure.system.power.subprocess.Popen", side_effect=FileNotFoundError):
            SystemdPowerControl().suspend()   # must not raise
