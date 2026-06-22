"""Windows network status (NetworkProbe) and a minimal NetworkControl.

The probe samples interfaces via psutil and classifies the active one by its
friendly name (Wi-Fi / Ethernet); the domain `PollingNetworkMonitor` turns it
into a live monitor that drives the top-bar indicator. Connect/disconnect aren't
implemented (the indicator is the parity win), so `NetworkControl` reports it
can't reconnect and its actions are no-ops.
"""

import logging
import socket

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
    """No-op control: the indicator is read-only on Windows for now."""

    def disconnect(self) -> None:
        logger.info("Network disconnect not implemented on Windows")

    def reconnect(self) -> None:
        logger.info("Network reconnect not implemented on Windows")

    def can_reconnect(self) -> bool:
        return False
