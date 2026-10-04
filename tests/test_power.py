"""Tests for the SystemdPowerControl adapter (systemctl)."""

from unittest.mock import MagicMock, patch

import pytest

from domain.system.silenced_power import SilencedPowerControl
from infrastructure.linux.power.power import SystemdPowerControl


class TestSystemdPowerControl:
    def test_suspend(self):
        with patch("infrastructure.linux.power.power.subprocess.Popen") as popen:
            SystemdPowerControl().suspend()
        popen.assert_called_once_with(["systemctl", "suspend"])

    def test_reboot(self):
        with patch("infrastructure.linux.power.power.subprocess.Popen") as popen:
            SystemdPowerControl().reboot()
        popen.assert_called_once_with(["systemctl", "reboot"])

    def test_poweroff(self):
        with patch("infrastructure.linux.power.power.subprocess.Popen") as popen:
            SystemdPowerControl().poweroff()
        popen.assert_called_once_with(["systemctl", "poweroff"])

    def test_swallows_errors(self):
        with patch("infrastructure.linux.power.power.subprocess.Popen", side_effect=FileNotFoundError):
            SystemdPowerControl().suspend()   # must not raise


class DeferredScheduler:
    def __init__(self):
        self.pending = []

    def call_later(self, delay_ms, callback):
        self.pending.append((delay_ms, callback))

    def fire(self):
        for _, callback in self.pending:
            callback()


POWER_VERBS = ("suspend", "reboot", "poweroff")


class TestSilencedPowerControl:
    @pytest.fixture
    def calls(self):
        return MagicMock()

    @pytest.fixture
    def scheduler(self):
        return DeferredScheduler()

    @pytest.fixture
    def power(self, calls, scheduler):
        return SilencedPowerControl(calls.power, calls.feedback, scheduler)

    @pytest.mark.parametrize("verb", POWER_VERBS)
    def test_silences_cues_before_the_power_action(self, power, calls, scheduler, verb):
        getattr(power, verb)()
        scheduler.fire()

        assert [name for name, _, _ in calls.mock_calls] == ["feedback.silence", f"power.{verb}"]

    @pytest.mark.parametrize("verb", POWER_VERBS)
    def test_the_power_action_waits_for_the_deferral(self, power, calls, scheduler, verb):
        getattr(power, verb)()

        getattr(calls.power, verb).assert_not_called()
        delay_ms, _ = scheduler.pending[0]
        assert delay_ms > 0
