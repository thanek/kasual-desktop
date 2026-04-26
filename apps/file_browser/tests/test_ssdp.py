"""Tests for SSDP icon selection logic in ssdp.py."""

import xml.etree.ElementTree as ET

import pytest

from ssdp import _best_icon_url

_NS_URI = "urn:schemas-upnp-org:device-1-0"
_NS     = {"d": _NS_URI}


def _make_device_xml(*icons) -> ET.Element:
    """
    Build a minimal UPnP device descriptor with the given icons.
    Each icon is a dict with keys: mime, width, height, url.
    """
    parts = ["<d:iconList>"]
    for ic in icons:
        parts.append(
            f"<d:icon>"
            f"<d:mimetype>{ic['mime']}</d:mimetype>"
            f"<d:width>{ic['width']}</d:width>"
            f"<d:height>{ic['height']}</d:height>"
            f"<d:url>{ic['url']}</d:url>"
            f"</d:icon>"
        )
    parts.append("</d:iconList>")
    xml = (
        f'<root xmlns:d="{_NS_URI}">'
        f'<d:device>'
        + "".join(parts) +
        f'</d:device>'
        f'</root>'
    )
    return ET.fromstring(xml)


class TestBestIconUrl:
    def test_returns_empty_when_no_icons(self):
        root = _make_device_xml()
        assert _best_icon_url(root, _NS, "http://srv") == ""

    def test_returns_absolute_url(self):
        root = _make_device_xml(
            {"mime": "image/png", "width": 64, "height": 64, "url": "/icons/icon.png"}
        )
        url = _best_icon_url(root, _NS, "http://srv:1234")
        assert url == "http://srv:1234/icons/icon.png"

    def test_prefers_png_over_jpeg_same_size(self):
        root = _make_device_xml(
            {"mime": "image/jpeg", "width": 128, "height": 128, "url": "/icon.jpg"},
            {"mime": "image/png",  "width": 128, "height": 128, "url": "/icon.png"},
        )
        url = _best_icon_url(root, _NS, "http://srv")
        assert url.endswith("/icon.png")

    def test_prefers_larger_icon(self):
        root = _make_device_xml(
            {"mime": "image/png", "width":  32, "height":  32, "url": "/small.png"},
            {"mime": "image/png", "width": 128, "height": 128, "url": "/large.png"},
        )
        url = _best_icon_url(root, _NS, "http://srv")
        assert url.endswith("/large.png")

    def test_penalises_oversized_over_256(self):
        # 512px: size = 256 - (512 - 256) = 0; loses to a 128px PNG
        root = _make_device_xml(
            {"mime": "image/png", "width": 512, "height": 512, "url": "/huge.png"},
            {"mime": "image/png", "width": 128, "height": 128, "url": "/ok.png"},
        )
        url = _best_icon_url(root, _NS, "http://srv")
        assert url.endswith("/ok.png")

    def test_ignores_unsupported_mime_types(self):
        root = _make_device_xml(
            {"mime": "image/gif", "width": 256, "height": 256, "url": "/icon.gif"},
        )
        assert _best_icon_url(root, _NS, "http://srv") == ""

    def test_skips_icon_with_empty_url(self):
        root = _make_device_xml(
            {"mime": "image/png", "width": 128, "height": 128, "url": ""},
        )
        assert _best_icon_url(root, _NS, "http://srv") == ""

    def test_exact_256_not_penalised(self):
        root = _make_device_xml(
            {"mime": "image/png", "width": 256, "height": 256, "url": "/256.png"},
            {"mime": "image/png", "width": 128, "height": 128, "url": "/128.png"},
        )
        url = _best_icon_url(root, _NS, "http://srv")
        assert url.endswith("/256.png")
