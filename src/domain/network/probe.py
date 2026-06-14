"""The minimal *pull* port for network backends that can only sample.

Some sources have no change events (an `nmcli` call, reading `/sys/class/net`,
systemd-networkd queries). They implement just `read()` here and are turned into
a full `NetworkMonitor` by the domain `PollingNetworkMonitor` — so the
change-detection logic stays in the domain rather than being re-written per
adapter. Event-driven backends (NetworkManager) skip this and implement
`NetworkMonitor` directly.
"""

from typing import Protocol

from domain.network.status import NetworkStatus


class NetworkProbe(Protocol):
    """Sample the current network status on demand (no change events)."""

    def read(self) -> NetworkStatus: ...
