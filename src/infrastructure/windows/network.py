"""Windows network status (NetworkProbe) and a NetworkControl.

The probe samples interfaces via psutil and classifies the active one by its
friendly name (Wi-Fi / Ethernet); the domain `PollingNetworkMonitor` turns it
into a live monitor that drives the top-bar indicator.

``disconnect()``/``reconnect()`` toggle the primary interface via ``netsh
interface set interface ... admin=disable|enable`` — the same mechanism the
Windows shell uses. ``netsh`` requires elevation, so the call is launched
through ``ShellExecuteEx`` with the ``runas`` verb: Windows shows a single UAC
prompt per action, the main Kasual process stays unelevated. The last interface
we took down is remembered in-process so ``reconnect()`` can restore exactly
that one (mirrors the Linux ``NMNetworkControl`` contract).
"""

import ctypes
import logging
import socket
import subprocess
from ctypes import wintypes

from domain.network.control import NetworkControl
from domain.network.status import NetworkKind, NetworkStatus

logger = logging.getLogger(__name__)

# Interface friendly-name fragments to ignore (virtual / loopback / tunnels).
_SKIP = (
    "loopback", "pseudo", "vethernet", "virtual", "vmware", "virtualbox",
    "vbox", "hyper-v", "bluetooth", "wsl", "docker", "tailscale", "tap-",
)


def _classify(name: str) -> NetworkKind:
    n = name.lower()
    if any(k in n for k in ("wi-fi", "wifi", "wlan", "wireless")):
        return NetworkKind.WIFI
    if any(k in n for k in ("ethernet", "eth", "lan")):
        return NetworkKind.ETHERNET
    return NetworkKind.UNKNOWN


def _ipv4(addrs) -> str | None:
    for a in addrs:
        if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254.")):
            return a.address
    return None


def _primary_interface() -> str | None:
    """Name of the active primary interface (matches the probe's preference:
    Ethernet > Wi-Fi > unknown), or None when offline."""
    try:
        import psutil
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except Exception as exc:
        logger.warning("Network interface lookup failed: %s", exc)
        return None

    best: str | None = None
    for name, st in stats.items():
        if not st.isup or any(s in name.lower() for s in _SKIP):
            continue
        if not _ipv4(addrs.get(name, [])):
            continue
        kind = _classify(name)
        if kind == NetworkKind.ETHERNET:
            return name
        best = best or name
    return best


# ── Elevated netsh via ShellExecuteEx (runas verb) ───────────────────────────

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE = 0
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",         wintypes.DWORD),
        ("fMask",          wintypes.ULONG),
        ("hwnd",           wintypes.HWND),
        ("lpVerb",         wintypes.LPCWSTR),
        ("lpFile",         wintypes.LPCWSTR),
        ("lpParameters",   wintypes.LPCWSTR),
        ("lpDirectory",    wintypes.LPCWSTR),
        ("nShow",          wintypes.INT),
        ("hInstApp",       wintypes.HINSTANCE),
        ("lpIDList",       ctypes.c_void_p),
        ("lpClass",        wintypes.LPCWSTR),
        ("hkeyClass",      wintypes.HKEY),
        ("dwHotKey",       wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess",       wintypes.HANDLE),
    ]


def _runas_netsh(interface: str, admin: str) -> bool:
    """Run ``netsh interface set interface name=... admin=<admin>`` elevated.

    Uses ``ShellExecuteEx`` with the ``runas`` verb: Windows shows a UAC prompt,
    the main Kasual process stays unelevated. Synchronously waits for the
    elevated process to exit so the caller knows whether it succeeded (rc==0).
    Returns True on success, False if the user declined UAC, the call failed,
    or the wait itself failed.
    """
    sei = _SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFO)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = "netsh.exe"
    sei.lpParameters = f"interface set interface name={interface} admin={admin}"
    sei.nShow = SW_HIDE

    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    if not ok:
        # Most common failure: the user clicked "No" on the UAC prompt
        # (ERROR_CANCELLED). There's no process to wait on.
        logger.info("netsh runas declined or failed (ShellExecuteEx returned 0)")
        return False

    try:
        hProcess = int(sei.hProcess or 0)
        if not hProcess:
            # No process handle (e.g. the verb was satisfied without spawning).
            # Treat as success — Windows already acted.
            return True
        # Block until the elevated netsh exits. 10 s is generous for a local
        # interface toggle; if it somehow hangs we give up and report False.
        rc = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 10_000)
        if rc == WAIT_FAILED or rc == WAIT_TIMEOUT:
            logger.warning("netsh elevated process wait failed/timeout (rc=%s)", rc)
            return False
        exit_code = wintypes.DWORD()
        if ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code)):
            if exit_code.value != 0:
                logger.warning("netsh elevated exit code %d for admin=%s on %r",
                               exit_code.value, admin, interface)
                return False
        return True
    finally:
        if hProcess:
            ctypes.windll.kernel32.CloseHandle(hProcess)


class WindowsNetworkProbe:
    """Sample the active connection (Ethernet preferred over Wi-Fi over unknown)."""

    def read(self) -> NetworkStatus:
        try:
            import psutil
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
        except Exception as exc:
            logger.warning("Network probe failed: %s", exc)
            return NetworkStatus.offline()

        best: NetworkStatus | None = None
        for name, st in stats.items():
            if not st.isup or any(s in name.lower() for s in _SKIP):
                continue
            ip = _ipv4(addrs.get(name, []))
            if not ip:
                continue
            kind = _classify(name)
            status = NetworkStatus(kind=kind, name=name, interface=name, ip_address=ip)
            if kind == NetworkKind.ETHERNET:
                return status           # wired wins
            best = best or status
        return best or NetworkStatus.offline()


class WindowsNetworkControl(NetworkControl):
    """Connect/disconnect the primary network interface via elevated ``netsh``.

    Mirrors the Linux ``NMNetworkControl`` contract: ``disconnect()`` brings the
    primary interface down and remembers it; ``reconnect()`` brings that
    interface back up; ``can_reconnect()`` reports whether there is one to
    restore. ``netsh interface set ... admin=`` requires elevation — the call
    is launched through ``ShellExecuteEx`` with the ``runas`` verb, so Windows
    shows a UAC prompt and the main Kasual process stays unelevated. If the user
    declines UAC the call fails gracefully (the overlay closes, the indicator
    stays, ``can_reconnect`` stays False so the overlay reflects reality).
    """

    def __init__(self) -> None:
        self._last_interface: str | None = None

    def disconnect(self) -> None:
        iface = _primary_interface()
        if not iface:
            logger.info("Network disconnect: no primary interface to take down")
            return
        if _runas_netsh(iface, "disable"):
            self._last_interface = iface
            logger.info("Network interface %r disabled", iface)
        else:
            # UAC declined or netsh failed — don't remember the interface, so
            # can_reconnect stays False and the overlay reflects reality.
            self._last_interface = None

    def reconnect(self) -> None:
        if not self._last_interface:
            logger.info("Network reconnect: no previously disabled interface")
            return
        iface = self._last_interface
        if _runas_netsh(iface, "enable"):
            self._last_interface = None
            logger.info("Network interface %r re-enabled", iface)

    def can_reconnect(self) -> bool:
        return self._last_interface is not None
