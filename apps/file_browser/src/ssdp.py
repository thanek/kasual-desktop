"""SSDP M-SEARCH discovery for UPnP MediaServer:1 (DLNA) devices."""

import socket
import time
import xml.etree.ElementTree as ET
from urllib.request import urlopen

_SSDP_ADDR = "239.255.255.250"
_SSDP_PORT = 1900
_MX = 3

_M_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {_SSDP_ADDR}:{_SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    f"MX: {_MX}\r\n"
    "ST: urn:schemas-upnp-org:device:MediaServer:1\r\n"
    "\r\n"
)


def _friendly_name(location: str) -> str | None:
    try:
        with urlopen(location, timeout=3) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        ns = {"d": "urn:schemas-upnp-org:device-1-0"}
        el = root.find(".//d:friendlyName", ns)
        return el.text if el is not None else None
    except Exception:
        return None


def discover(timeout: float = 5.0) -> list[dict]:
    """Return list of {'name': str, 'location': str} for each found DLNA server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)

    try:
        sock.sendto(_M_SEARCH.encode(), (_SSDP_ADDR, _SSDP_PORT))
        seen: set[str] = set()
        servers: list[dict] = []
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue

            headers: dict[str, str] = {}
            for line in data.decode(errors="replace").split("\r\n")[1:]:
                if ":" in line:
                    k, _, v = line.partition(":")
                    headers[k.strip().upper()] = v.strip()

            location = headers.get("LOCATION", "")
            usn = headers.get("USN", location)
            if not location or usn in seen:
                continue
            seen.add(usn)

            name = _friendly_name(location) or location
            servers.append({"name": name, "location": location})

        return servers
    finally:
        sock.close()
