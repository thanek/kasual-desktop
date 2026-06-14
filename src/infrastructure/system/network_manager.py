"""NetworkManager-backed `NetworkMonitor` (KDE's default network stack).

Implements the domain `NetworkMonitor` port over NetworkManager's D-Bus API on
the SYSTEM bus. Event-driven: it subscribes to NM change signals and re-resolves
the active connection into a domain `NetworkStatus`, emitting on the GUI thread
(QtDBus delivers there) — same `EventEmitter`/`Unsubscribe` contract as the other
adapters.

All NetworkManager-specific knowledge (object paths, interface names, device-type
codes) lives here; the domain never sees it. The IPv4 address is read locally
from the resolved interface via an ioctl, avoiding NM's nested `aa{sv}` D-Bus
type — a pure implementation detail.
"""

from __future__ import annotations

import fcntl
import logging
import socket
import struct
from collections.abc import Callable
from typing import _ProtocolMeta  # type: ignore[attr-defined]

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusObjectPath

from domain.network.control import NetworkControl
from domain.network.monitor import NetworkMonitor
from domain.network.status import NetworkKind, NetworkStatus
from domain.shared.event_emitter import EventEmitter, Unsubscribe

logger = logging.getLogger(__name__)


class _Meta(type(QObject), _ProtocolMeta):
    """Combined metaclass so a QObject can declare it implements a Protocol port."""


_NM_SVC   = "org.freedesktop.NetworkManager"
_NM_PATH  = "/org/freedesktop/NetworkManager"
_NM_IFACE = "org.freedesktop.NetworkManager"

_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_AC_IFACE    = "org.freedesktop.NetworkManager.Connection.Active"
_DEV_IFACE   = "org.freedesktop.NetworkManager.Device"
_WIFI_IFACE  = "org.freedesktop.NetworkManager.Device.Wireless"
_AP_IFACE    = "org.freedesktop.NetworkManager.AccessPoint"

_TYPE_KIND = {
    "802-11-wireless": NetworkKind.WIFI,
    "802-3-ethernet":  NetworkKind.ETHERNET,
}

_SIOCGIFADDR = 0x8915   # ioctl: get interface IPv4 address


class NMNetworkMonitor(QObject, NetworkMonitor, metaclass=_Meta):
    """`NetworkMonitor` over NetworkManager's system-bus D-Bus API."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._emitter: EventEmitter[NetworkStatus] = EventEmitter()
        self._bus = QDBusConnection.systemBus()
        # Re-resolve on NM connectivity / primary-connection changes.
        for iface, name in (
            (_NM_IFACE, "StateChanged"),
            (_PROPS_IFACE, "PropertiesChanged"),
        ):
            ok = self._bus.connect(_NM_SVC, _NM_PATH, iface, name, self._on_nm_signal)
            if not ok:
                logger.warning("NM signal subscribe failed: %s.%s", iface, name)
        self._status = self._resolve()

    # ── NetworkMonitor port ──────────────────────────────────────────────────

    def current(self) -> NetworkStatus:
        return self._status

    def on_changed(
        self, handler: Callable[[NetworkStatus], None]
    ) -> Unsubscribe:
        return self._emitter.subscribe(handler)

    # ── Change handling ──────────────────────────────────────────────────────

    @pyqtSlot()
    @pyqtSlot("uint")
    @pyqtSlot(str, "QVariantMap", "QStringList")
    def _on_nm_signal(self, *_args) -> None:
        """Any NM state/property change → re-resolve and emit on real change."""
        new = self._resolve()
        if new != self._status:
            self._status = new
            self._emitter.emit(new)

    # ── Resolving NM → NetworkStatus (all NM specifics live here) ─────────────

    def _resolve(self) -> NetworkStatus:
        try:
            primary = self._path(_NM_PATH, _NM_IFACE, "PrimaryConnection")
            if not primary or primary == "/":
                return NetworkStatus.offline()

            ctype = self._str(primary, _AC_IFACE, "Type")
            kind = _TYPE_KIND.get(ctype, NetworkKind.UNKNOWN)
            name = self._str(primary, _AC_IFACE, "Id")

            interface = ""
            signal: int | None = None
            devices = self._paths(primary, _AC_IFACE, "Devices")
            if devices:
                dev = devices[0]
                interface = self._str(dev, _DEV_IFACE, "Interface")
                if kind is NetworkKind.WIFI:
                    name, signal = self._wifi_details(dev, name)

            ip = self._iface_ipv4(interface) if interface else None
            return NetworkStatus(
                kind=kind, name=name, interface=interface,
                ip_address=ip, signal=signal,
            )
        except Exception as exc:
            logger.debug("Network resolve failed: %s", exc)
            return NetworkStatus.offline()

    def _wifi_details(self, device: str, fallback_name: str) -> tuple[str, int | None]:
        ap = self._path(device, _WIFI_IFACE, "ActiveAccessPoint")
        if not ap or ap == "/":
            return fallback_name, None
        strength = self._get(ap, _AP_IFACE, "Strength")
        signal = int(strength) if strength is not None else None
        ssid = self._ssid(self._get(ap, _AP_IFACE, "Ssid"))
        return (ssid or fallback_name), signal

    # ── D-Bus property helpers ───────────────────────────────────────────────

    def _get(self, path: str, iface: str, prop: str):
        reply = QDBusInterface(_NM_SVC, path, _PROPS_IFACE, self._bus).call(
            "Get", iface, prop
        )
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            return None
        args = reply.arguments()
        return args[0] if args else None

    def _str(self, path: str, iface: str, prop: str) -> str:
        value = self._get(path, iface, prop)
        return str(value) if value is not None else ""

    def _path(self, path: str, iface: str, prop: str) -> str:
        value = self._get(path, iface, prop)
        if isinstance(value, QDBusObjectPath):
            return value.path()
        return str(value) if value else ""

    def _paths(self, path: str, iface: str, prop: str) -> list[str]:
        value = self._get(path, iface, prop)
        if not value:
            return []
        return [p.path() if isinstance(p, QDBusObjectPath) else str(p) for p in value]

    @staticmethod
    def _ssid(raw) -> str:
        """Decode an NM SSID (an array of bytes / QByteArray) to text."""
        if raw is None:
            return ""
        try:
            return bytes(raw).decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _iface_ipv4(ifname: str) -> str | None:
        """The interface's IPv4 via SIOCGIFADDR — avoids NM's nested IP4Config
        D-Bus structure. Linux-specific (KD only targets Linux/KDE)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            packed = struct.pack("256s", ifname[:15].encode())
            addr = fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, packed)[20:24]
            return socket.inet_ntoa(addr)
        except OSError:
            return None


class NMNetworkControl(NetworkControl):
    """`NetworkControl` over NetworkManager's system-bus D-Bus API.

    `disconnect()` brings the primary connection down with `Device.Disconnect`,
    which NM treats as a deliberate user action — it suppresses autoconnect so
    the link stays down (a plain `DeactivateConnection` would auto-reconnect).
    It first remembers the connection profile + device behind it, so that
    `reconnect()` can re-`ActivateConnection` exactly that one. The memory is
    in-process only: after a disconnect we can restore, until we do (or exit).
    """

    def __init__(self) -> None:
        self._bus = QDBusConnection.systemBus()
        # (connection-settings path, device path) of the last link we took down.
        self._last: tuple[str, str] | None = None

    def disconnect(self) -> None:
        primary = self._path(_NM_PATH, _NM_IFACE, "PrimaryConnection")
        if not primary or primary == "/":
            return
        connection = self._path(primary, _AC_IFACE, "Connection")
        devices = self._paths(primary, _AC_IFACE, "Devices")
        if connection and devices:
            self._last = (connection, devices[0])
        for device in devices:
            QDBusInterface(_NM_SVC, device, _DEV_IFACE, self._bus).call("Disconnect")

    def reconnect(self) -> None:
        if self._last is None:
            return
        connection, device = self._last
        QDBusInterface(_NM_SVC, _NM_PATH, _NM_IFACE, self._bus).call(
            "ActivateConnection",
            QDBusObjectPath(connection),
            QDBusObjectPath(device),
            QDBusObjectPath("/"),
        )
        self._last = None

    def can_reconnect(self) -> bool:
        return self._last is not None

    # ── D-Bus property reads (object-path valued) ────────────────────────────

    def _path(self, path: str, iface: str, prop: str) -> str:
        value = self._get(path, iface, prop)
        if isinstance(value, QDBusObjectPath):
            return value.path()
        return str(value) if value else ""

    def _paths(self, path: str, iface: str, prop: str) -> list[str]:
        value = self._get(path, iface, prop)
        if not value:
            return []
        return [p.path() if isinstance(p, QDBusObjectPath) else str(p) for p in value]

    def _get(self, path: str, iface: str, prop: str):
        reply = QDBusInterface(_NM_SVC, path, _PROPS_IFACE, self._bus).call(
            "Get", iface, prop
        )
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            return None
        args = reply.arguments()
        return args[0] if args else None
