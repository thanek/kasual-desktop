"""The network connection state — the platform-agnostic value object.

Pure Python — no Qt, no D-Bus, no NetworkManager. Whatever backend observes the
system (NetworkManager, nmcli, systemd-networkd, /sys, …) maps its own data into
this; the rest of the app only ever sees a `NetworkStatus`.

Detail fields are optional on purpose: a backend fills only what it can resolve
(e.g. a `/sys` reader may know the interface and kind but not the SSID or signal),
and the presentation (`domain.network.view`) simply omits what is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class NetworkKind(StrEnum):
    """How the machine is connected — drives which icon the top bar shows."""

    WIFI     = "wifi"
    ETHERNET = "ethernet"
    OFFLINE  = "offline"
    # Connected, but the backend could not classify it as Wi-Fi/Ethernet (VPN,
    # mobile broadband, a bridge, …). Lets any implementation report "online,
    # type N/A" without being forced into a wrong category.
    UNKNOWN  = "unknown"


@dataclass(frozen=True)
class NetworkStatus:
    """A snapshot of the active connection. Immutable; equality drives change
    detection (see `domain.network.polling.PollingNetworkMonitor`)."""

    kind:       NetworkKind
    name:       str        = ""     # SSID (Wi-Fi) or connection id
    interface:  str        = ""     # e.g. wlan0 / eth0
    ip_address: str | None = None   # primary IPv4, when known
    signal:     int | None = None   # Wi-Fi strength 0–100, when applicable

    @property
    def online(self) -> bool:
        return self.kind is not NetworkKind.OFFLINE

    @classmethod
    def offline(cls) -> "NetworkStatus":
        return cls(kind=NetworkKind.OFFLINE)
