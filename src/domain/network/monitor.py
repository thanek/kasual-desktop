"""The network-status port the Desktop observes.

The single seam every backend implements — backend-agnostic by design, so the
chosen NetworkManager adapter is just one possibility (nmcli, systemd-networkd,
a `/sys` reader or a test fake all fit the same contract). It says nothing about
D-Bus, polling or threading: the implementation is responsible for delivering
`on_changed` on the GUI thread, exactly like the other observation ports.

A pull-only backend need not implement this directly — it can implement the
smaller `domain.network.probe.NetworkProbe` and be wrapped by the domain
`PollingNetworkMonitor`, which turns periodic samples into change events.
"""

from collections.abc import Callable
from typing import Protocol

from domain.shared.event_emitter import Unsubscribe
from domain.network.status import NetworkStatus


class NetworkMonitor(Protocol):
    """Current network status plus notification when it changes."""

    def current(self) -> NetworkStatus: ...
    def on_changed(
        self, handler: Callable[[NetworkStatus], None]
    ) -> Unsubscribe: ...
