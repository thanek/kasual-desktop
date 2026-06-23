"""Tests for the Windows network probe and elevated netsh control.

Covers:

  - ``_classify`` — friendly-name fragments → ``NetworkKind``.
  - ``_ipv4`` — first non-loopback, non-link-local AF_INET address; None when
    absent.
  - ``_SKIP`` — virtual / loopback / tunnel interfaces filtered out.
  - ``_primary_interface`` — Ethernet preferred over Wi-Fi over unknown; None
    when offline; psutil exception → None.
  - ``WindowsNetworkProbe.read`` — same preference order; offline when no up+
    IP interface; psutil exception → ``NetworkStatus.offline()``.
  - ``_runas_netsh`` — ``ShellExecuteEx`` with ``runas`` verb; UAC declined
    (returns 0) → False; no process handle → True; ``WAIT_TIMEOUT`` /
    ``WAIT_FAILED`` → False; non-zero exit code → False; ``CloseHandle`` in
    finally.
  - ``WindowsNetworkControl`` — ``disconnect()`` remembers the interface only
    on success; ``reconnect()`` restores exactly the disabled one;
    ``can_reconnect`` reports the remembered state.

Skipped on non-Windows: ``ctypes.windll`` and ``ShellExecuteEx`` are
Windows-only.
"""

import socket
import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.windll", allow_module_level=True)

from domain.network.status import NetworkKind, NetworkStatus
from infrastructure.windows.network import (
    WAIT_FAILED, WAIT_TIMEOUT, _classify, _ipv4, _primary_interface,
    _runas_netsh, _SKIP, WindowsNetworkControl, WindowsNetworkProbe,
)


# ── _classify ─────────────────────────────────────────────────────────────────

class TestClassify:
    def test_wifi_variants(self):
        for name in ("Wi-Fi", "WiFi", "WLAN", "Wireless Network"):
            assert _classify(name) == NetworkKind.WIFI

    def test_ethernet_variants(self):
        for name in ("Ethernet", "Ethernet0", "eth0", "LAN"):
            assert _classify(name) == NetworkKind.ETHERNET

    def test_unknown_for_others(self):
        for name in ("Bluetooth", "VPN", "Tailscale", "Random"):
            assert _classify(name) == NetworkKind.UNKNOWN

    def test_case_insensitive(self):
        assert _classify("WI-FI") == NetworkKind.WIFI
        assert _classify("ETHERNET") == NetworkKind.ETHERNET


# ── _ipv4 ─────────────────────────────────────────────────────────────────────

class TestIpv4:
    def _addr(self, address, family=socket.AF_INET):
        return MagicMock(family=family, address=address)

    def test_returns_first_valid_ipv4(self):
        addrs = [self._addr("127.0.0.1"), self._addr("192.168.1.10")]
        assert _ipv4(addrs) == "192.168.1.10"

    def test_skips_link_local(self):
        addrs = [self._addr("169.254.1.5"), self._addr("10.0.0.5")]
        assert _ipv4(addrs) == "10.0.0.5"

    def test_returns_none_when_only_loopback(self):
        assert _ipv4([self._addr("127.0.0.1")]) is None

    def test_returns_none_when_only_link_local(self):
        assert _ipv4([self._addr("169.254.1.5")]) is None

    def test_returns_none_when_empty(self):
        assert _ipv4([]) is None

    def test_skips_ipv6(self):
        addrs = [MagicMock(family=socket.AF_INET6, address="::1")]
        assert _ipv4(addrs) is None


# ── _SKIP — virtual / loopback / tunnels ─────────────────────────────────────

class TestSkipFilter:
    def test_skip_set_contains_known_virtual_fragments(self):
        for fragment in ("loopback", "vmware", "wsl", "docker",
                         "tailscale", "virtual", "bluetooth"):
            assert fragment in _SKIP


# ── _primary_interface ────────────────────────────────────────────────────────

class TestPrimaryInterface:
    def _setup(self, interfaces):
        """Build a psutil mock from a list of (name, stats, addrs) tuples."""
        stats = {n: s for n, s, _ in interfaces}
        addrs = {n: a for n, _, a in interfaces}
        psutil_mod = MagicMock()
        psutil_mod.net_if_stats.return_value = stats
        psutil_mod.net_if_addrs.return_value = addrs
        return patch.dict("sys.modules", {"psutil": psutil_mod})

    def test_ethernet_preferred_over_wifi(self):
        ifaces = [
            ("Wi-Fi", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="192.168.1.5")]),
            ("Ethernet", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="10.0.0.5")]),
        ]
        with self._setup(ifaces):
            assert _primary_interface() == "Ethernet"

    def test_wifi_when_no_ethernet(self):
        ifaces = [
            ("Wi-Fi", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="192.168.1.5")]),
        ]
        with self._setup(ifaces):
            assert _primary_interface() == "Wi-Fi"

    def test_none_when_offline(self):
        ifaces = [
            ("Ethernet", MagicMock(isup=False),
             [MagicMock(family=socket.AF_INET, address="10.0.0.5")]),
        ]
        with self._setup(ifaces):
            assert _primary_interface() is None

    def test_none_when_no_ipv4(self):
        ifaces = [
            ("Ethernet", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET6, address="::1")]),
        ]
        with self._setup(ifaces):
            assert _primary_interface() is None

    def test_skips_virtual_interfaces(self):
        ifaces = [
            ("vEthernet (WSL)", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="172.20.0.1")]),
            ("Ethernet", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="10.0.0.5")]),
        ]
        with self._setup(ifaces):
            assert _primary_interface() == "Ethernet"

    def test_psutil_exception_returns_none(self):
        psutil_mod = MagicMock()
        psutil_mod.net_if_stats.side_effect = OSError("denied")
        with patch.dict("sys.modules", {"psutil": psutil_mod}):
            assert _primary_interface() is None


# ── WindowsNetworkProbe.read ──────────────────────────────────────────────────

class TestNetworkProbeRead:
    def _setup(self, interfaces):
        stats = {n: s for n, s, _ in interfaces}
        addrs = {n: a for n, _, a in interfaces}
        psutil_mod = MagicMock()
        psutil_mod.net_if_stats.return_value = stats
        psutil_mod.net_if_addrs.return_value = addrs
        return patch.dict("sys.modules", {"psutil": psutil_mod})

    def test_ethernet_wins(self):
        ifaces = [
            ("Wi-Fi", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="192.168.1.5")]),
            ("Ethernet", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="10.0.0.5")]),
        ]
        with self._setup(ifaces):
            status = WindowsNetworkProbe().read()
        assert status.kind == NetworkKind.ETHERNET
        assert status.ip_address == "10.0.0.5"
        assert status.online

    def test_wifi_fallback(self):
        ifaces = [
            ("Wi-Fi", MagicMock(isup=True),
             [MagicMock(family=socket.AF_INET, address="192.168.1.5")]),
        ]
        with self._setup(ifaces):
            status = WindowsNetworkProbe().read()
        assert status.kind == NetworkKind.WIFI
        assert status.name == "Wi-Fi"

    def test_offline_when_no_up_interface(self):
        ifaces = [
            ("Ethernet", MagicMock(isup=False),
             [MagicMock(family=socket.AF_INET, address="10.0.0.5")]),
        ]
        with self._setup(ifaces):
            status = WindowsNetworkProbe().read()
        assert status.online is False
        assert status.kind == NetworkKind.OFFLINE

    def test_offline_when_psutil_raises(self):
        psutil_mod = MagicMock()
        psutil_mod.net_if_stats.side_effect = OSError
        with patch.dict("sys.modules", {"psutil": psutil_mod}):
            status = WindowsNetworkProbe().read()
        assert status.online is False


# ── _runas_netsh ──────────────────────────────────────────────────────────────

class TestRunasNetsh:
    def _run(self, shell_exec_ok=1, hProcess=0x100, wait_rc=0, exit_code=0):
        """Run _runas_netsh with mocked Win32 calls; returns (result, mocks)."""
        with patch("infrastructure.windows.network._shell32") as shell32, \
             patch("infrastructure.windows.network._kernel32") as kernel32, \
             patch("infrastructure.windows.network.wintypes") as wintypes, \
             patch("infrastructure.windows.network.ctypes.byref", lambda o: o), \
             patch("infrastructure.windows.network.ctypes.sizeof", return_value=64):
            shell32.ShellExecuteExW.return_value = shell_exec_ok
            kernel32.WaitForSingleObject.return_value = wait_rc
            # wintypes.DWORD() is constructed then filled by GetExitCodeProcess.
            ec = MagicMock()
            ec.value = exit_code
            wintypes.DWORD.return_value = ec
            kernel32.GetExitCodeProcess.return_value = 1   # success
            # ShellExecuteExW writes hProcess back through the struct byref.
            def _sei(sei):
                sei.hProcess = hProcess
                return shell_exec_ok
            shell32.ShellExecuteExW.side_effect = _sei
            result = _runas_netsh("Ethernet", "disable")
        return result, shell32, kernel32

    def test_success_when_exit_code_zero(self):
        result, _, _ = self._run(wait_rc=0, exit_code=0)
        assert result is True

    def test_uac_declined_returns_false(self):
        # ShellExecuteExW returns 0 → the user clicked "No" on the UAC prompt.
        result, shell32, kernel32 = self._run(shell_exec_ok=0, hProcess=0)
        assert result is False
        # No process to wait on.
        kernel32.WaitForSingleObject.assert_not_called()

    def test_no_process_handle_treated_as_success(self):
        # Some verbs are satisfied without spawning a process.
        result, _, _ = self._run(hProcess=0, wait_rc=0)
        assert result is True

    def test_wait_timeout_returns_false(self):
        result, _, _ = self._run(wait_rc=WAIT_TIMEOUT)
        assert result is False

    def test_wait_failed_returns_false(self):
        result, _, _ = self._run(wait_rc=WAIT_FAILED)
        assert result is False

    def test_nonzero_exit_code_returns_false(self):
        result, _, _ = self._run(wait_rc=0, exit_code=1)
        assert result is False

    def test_close_handle_called_in_finally(self):
        # CloseHandle must be called even on the success path.
        _, _, kernel32 = self._run(hProcess=0x200, wait_rc=0, exit_code=0)
        kernel32.CloseHandle.assert_called_once_with(0x200)


# ── WindowsNetworkControl ─────────────────────────────────────────────────────

class TestWindowsNetworkControl:
    def test_can_reconnect_false_initially(self):
        assert WindowsNetworkControl().can_reconnect() is False

    def test_disconnect_remembers_interface_on_success(self):
        ctrl = WindowsNetworkControl()
        with patch("infrastructure.windows.network._primary_interface",
                   return_value="Ethernet"), \
             patch("infrastructure.windows.network._runas_netsh",
                   return_value=True):
            ctrl.disconnect()
        assert ctrl.can_reconnect() is True

    def test_disconnect_does_not_remember_on_failure(self):
        # UAC declined or netsh failed — don't remember, so can_reconnect stays
        # False and the overlay reflects reality.
        ctrl = WindowsNetworkControl()
        with patch("infrastructure.windows.network._primary_interface",
                   return_value="Ethernet"), \
             patch("infrastructure.windows.network._runas_netsh",
                   return_value=False):
            ctrl.disconnect()
        assert ctrl.can_reconnect() is False

    def test_disconnect_noop_when_no_primary_interface(self):
        ctrl = WindowsNetworkControl()
        with patch("infrastructure.windows.network._primary_interface",
                   return_value=None), \
             patch("infrastructure.windows.network._runas_netsh") as runas:
            ctrl.disconnect()
        runas.assert_not_called()
        assert ctrl.can_reconnect() is False

    def test_reconnect_restores_disabled_interface(self):
        ctrl = WindowsNetworkControl()
        ctrl._last_interface = "Ethernet"
        with patch("infrastructure.windows.network._runas_netsh",
                   return_value=True) as runas:
            ctrl.reconnect()
        # The same interface that was disabled is brought back up (admin=enable).
        assert runas.call_args.args == ("Ethernet", "enable")
        # Success clears the remembered interface.
        assert ctrl.can_reconnect() is False

    def test_reconnect_noop_when_nothing_disabled(self):
        ctrl = WindowsNetworkControl()
        with patch("infrastructure.windows.network._runas_netsh") as runas:
            ctrl.reconnect()
        runas.assert_not_called()

    def test_reconnect_failure_keeps_interface_for_retry(self):
        # If the re-enable fails (e.g. user declines UAC again), keep the
        # remembered interface so the user can retry.
        ctrl = WindowsNetworkControl()
        ctrl._last_interface = "Wi-Fi"
        with patch("infrastructure.windows.network._runas_netsh",
                   return_value=False):
            ctrl.reconnect()
        assert ctrl.can_reconnect() is True

