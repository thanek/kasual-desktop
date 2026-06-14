"""The *command* port for the active network connection — turning it on/off.

The read-only counterpart of `domain.network.monitor.NetworkMonitor`: the monitor
*observes* the connection, this one *acts* on it. Backend-agnostic by design — the
chosen NetworkManager adapter is one possibility (nmcli, systemd-networkd or a
test fake all fit the same contract). It says nothing about D-Bus or devices.

`disconnect()` brings the primary connection down; `reconnect()` restores the last
one taken down this way, and `can_reconnect()` reports whether there is one to
restore (so the presentation can disable the button when there is nothing to do).
"""

from typing import Protocol


class NetworkControl(Protocol):
    """Activate / deactivate the primary network connection."""

    def disconnect(self) -> None: ...
    def reconnect(self) -> None: ...
    def can_reconnect(self) -> bool: ...
