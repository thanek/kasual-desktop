"""Tests for WindowsPowerControl — sleep / restart / shut down.

Sleep uses ``SetSuspendState`` (powrprof); restart/shutdown shell out to the
system ``shutdown`` tool. All Win32 calls and subprocess.run are mocked — no
real power action is ever triggered.

Skipped on non-Windows: ``ctypes.windll.powrprof`` is Windows-only.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from infrastructure.windows.power import WindowsPowerControl


class TestSuspend:
    def test_calls_set_suspend_state_with_false_false_false(self):
        with patch("infrastructure.windows.power.ctypes.windll") as windll:
            WindowsPowerControl().suspend()
        windll.powrprof.SetSuspendState.assert_called_once_with(0, 0, 0)

    def test_swallows_exception(self):
        with patch("infrastructure.windows.power.ctypes.windll") as windll:
            windll.powrprof.SetSuspendState.side_effect = OSError
            WindowsPowerControl().suspend()   # must not raise


class TestReboot:
    def test_calls_shutdown_with_r_flag(self):
        with patch("infrastructure.windows.power.subprocess.run") as run:
            WindowsPowerControl().reboot()
        args = run.call_args.args[0]
        assert args[:2] == ["shutdown", "/r"]
        assert "/t" in args and "0" in args

    def test_passes_create_no_window_flag(self):
        with patch("infrastructure.windows.power.subprocess.run") as run:
            WindowsPowerControl().reboot()
        assert run.call_args.kwargs["creationflags"] == 0x08000000

    def test_swallows_exception(self):
        with patch("infrastructure.windows.power.subprocess.run",
                   side_effect=OSError):
            WindowsPowerControl().reboot()   # must not raise


class TestPoweroff:
    def test_calls_shutdown_with_s_flag(self):
        with patch("infrastructure.windows.power.subprocess.run") as run:
            WindowsPowerControl().poweroff()
        args = run.call_args.args[0]
        assert args[:2] == ["shutdown", "/s"]
        assert "/t" in args and "0" in args

    def test_swallows_exception(self):
        with patch("infrastructure.windows.power.subprocess.run",
                   side_effect=OSError):
            WindowsPowerControl().poweroff()   # must not raise


class TestShutdownHelper:
    def test_check_false_does_not_raise(self):
        # The _shutdown helper uses check=False so a failed shutdown doesn't
        # raise — the error is only logged.
        with patch("infrastructure.windows.power.subprocess.run") as run:
            WindowsPowerControl()._shutdown("/s")
        assert run.call_args.kwargs["check"] is False
