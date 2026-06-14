"""Presentation vocabulary for the network status — icon + popup content.

Pure, Qt-free. Decides *which* glyph the top bar shows for a kind and *what* the
info popup reads, given a `NetworkStatus`. Lives in the domain because it is the
feature's vocabulary, not an adapter — its only outward need is translation,
taken through `support.i18n.translate` (the calls double as extraction markers,
exactly like `domain.system.action_view`).
"""

from dataclasses import dataclass

from domain.network.status import NetworkKind, NetworkStatus
from domain.shared.text import truncate
from support.i18n import translate

# qtawesome glyphs (verified available); swap here without touching adapters.
_ICONS = {
    NetworkKind.WIFI:     "fa5s.wifi",
    NetworkKind.ETHERNET: "fa5s.network-wired",
    NetworkKind.OFFLINE:  "mdi.wifi-off",
    NetworkKind.UNKNOWN:  "fa5s.globe",
}

_KIND_LABELS = {
    NetworkKind.WIFI:     "Wi-Fi",
    NetworkKind.ETHERNET: "Ethernet",
    NetworkKind.UNKNOWN:  "Connected",
}


def icon_for(kind: NetworkKind) -> str:
    """The top-bar glyph for *kind* (falls back to the offline icon)."""
    return _ICONS.get(kind, _ICONS[NetworkKind.OFFLINE])


def title() -> str:
    return translate("Kasual Desktop", "Network")


def info_lines(status: NetworkStatus) -> list[tuple[str, str]]:
    """(label, value) rows for the info popup, omitting fields the backend left
    empty. Offline collapses to a single status line."""
    if not status.online:
        return [(
            translate("Kasual Desktop", "Status"),
            translate("Kasual Desktop", "Not connected"),
        )]

    rows: list[tuple[str, str]] = [
        (translate("Kasual Desktop", "Type"),
         translate("Kasual Desktop", _KIND_LABELS.get(status.kind, "Connected"))),
    ]
    if status.name:
        label = translate("Kasual Desktop", "Network") if status.kind is NetworkKind.WIFI else (
            translate("Kasual Desktop", "Connection"))
        rows.append((translate("Kasual Desktop", label), truncate(status.name, 40)))
    if status.signal is not None:
        rows.append((translate("Kasual Desktop", "Signal"), f"{status.signal}%"))
    if status.ip_address:
        rows.append((translate("Kasual Desktop", "IP address"), status.ip_address))
    if status.interface:
        rows.append((translate("Kasual Desktop", "Interface"), status.interface))
    return rows


@dataclass(frozen=True)
class ConnectButton:
    """How the connect/disconnect toggle should present for the current state:
    its localized `label`, whether activating it *reconnects* (vs disconnects),
    and whether it is `enabled` (usable)."""

    label:     str
    reconnect: bool
    enabled:   bool


def connect_button(status: NetworkStatus, can_reconnect: bool) -> ConnectButton:
    """The toggle for *status*: "Disconnect" while online, otherwise "Connect"
    to restore the last connection — disabled when there is none to restore."""
    if status.online:
        return ConnectButton(
            translate("Kasual Desktop", "Disconnect"), reconnect=False, enabled=True,
        )
    return ConnectButton(
        translate("Kasual Desktop", "Connect"), reconnect=True, enabled=can_reconnect,
    )
