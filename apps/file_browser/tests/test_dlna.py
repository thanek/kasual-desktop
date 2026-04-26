"""Tests for DLNA XML parsing in dlna.py (no network access)."""

import html
from unittest.mock import MagicMock, patch

import pytest

from dlna import DlnaEntry, browse, get_control_url


# ── Helpers ───────────────────────────────────────────────────────────────────

_NS_DIDL = 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
_NS_DC   = 'http://purl.org/dc/elements/1.1/'
_NS_UPNP = 'urn:schemas-upnp-org:metadata-1-0/upnp/'


def _soap(didl_xml: str) -> bytes:
    """Wrap DIDL-Lite XML in a minimal SOAP BrowseResponse envelope."""
    return f"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <Result>{html.escape(didl_xml)}</Result>
    </u:BrowseResponse>
  </s:Body>
</s:Envelope>""".encode()


def _mock_urlopen(response_bytes: bytes):
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── DlnaEntry ─────────────────────────────────────────────────────────────────

class TestDlnaEntry:
    def test_defaults(self):
        e = DlnaEntry(id="1", title="Track", is_container=False)
        assert e.mime_type == ""
        assert e.resource_url == ""
        assert e.thumbnail_url == ""

    def test_container_flag(self):
        assert DlnaEntry(id="1", title="Folder", is_container=True).is_container
        assert not DlnaEntry(id="1", title="File", is_container=False).is_container


# ── browse() ─────────────────────────────────────────────────────────────────

class TestBrowse:
    def test_returns_empty_on_network_error(self):
        with patch("dlna.urlopen", side_effect=OSError("unreachable")):
            assert browse("http://fake/ctrl") == []

    def test_returns_empty_on_malformed_envelope(self):
        resp = _mock_urlopen(b"not xml at all")
        with patch("dlna.urlopen", return_value=resp):
            assert browse("http://fake/ctrl") == []

    def test_parses_audio_item(self):
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <item id="i1" parentID="0" restricted="1">
    <dc:title>Track 1</dc:title>
    <res protocolInfo="http-get:*:audio/mpeg:*">http://srv/track.mp3</res>
  </item>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert len(entries) == 1
        e = entries[0]
        assert e.id == "i1"
        assert e.title == "Track 1"
        assert not e.is_container
        assert e.mime_type == "audio/mpeg"
        assert e.resource_url == "http://srv/track.mp3"

    def test_parses_container(self):
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <container id="c1" parentID="0" childCount="3" restricted="1">
    <dc:title>Albums</dc:title>
  </container>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert len(entries) == 1
        e = entries[0]
        assert e.id == "c1"
        assert e.title == "Albums"
        assert e.is_container

    def test_parses_mixed_items_and_containers(self):
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <container id="c1" parentID="0" restricted="1">
    <dc:title>Folder</dc:title>
  </container>
  <item id="i1" parentID="0" restricted="1">
    <dc:title>Song</dc:title>
    <res protocolInfo="http-get:*:audio/flac:*">http://srv/song.flac</res>
  </item>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert len(entries) == 2
        assert entries[0].is_container
        assert not entries[1].is_container

    def test_thumbnail_from_albumarturi(self):
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <item id="i1" parentID="0" restricted="1">
    <dc:title>Track</dc:title>
    <upnp:albumArtURI>http://srv/cover.jpg</upnp:albumArtURI>
    <res protocolInfo="http-get:*:audio/mpeg:*">http://srv/t.mp3</res>
  </item>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert entries[0].thumbnail_url == "http://srv/cover.jpg"

    def test_thumbnail_from_jpeg_tn_res(self):
        """Falls back to JPEG_TN <res> when no albumArtURI."""
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <item id="i1" parentID="0" restricted="1">
    <dc:title>Track</dc:title>
    <res protocolInfo="http-get:*:audio/mpeg:*">http://srv/t.mp3</res>
    <res protocolInfo="http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN">http://srv/thumb.jpg</res>
  </item>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert entries[0].thumbnail_url == "http://srv/thumb.jpg"
        assert entries[0].resource_url  == "http://srv/t.mp3"

    def test_albumarturi_takes_precedence_over_tn_res(self):
        didl = f"""\
<DIDL-Lite xmlns="{_NS_DIDL}" xmlns:dc="{_NS_DC}" xmlns:upnp="{_NS_UPNP}">
  <item id="i1" parentID="0" restricted="1">
    <dc:title>Track</dc:title>
    <upnp:albumArtURI>http://srv/art.jpg</upnp:albumArtURI>
    <res protocolInfo="http-get:*:audio/mpeg:*">http://srv/t.mp3</res>
    <res protocolInfo="http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN">http://srv/tn.jpg</res>
  </item>
</DIDL-Lite>"""
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            entries = browse("http://fake/ctrl")

        assert entries[0].thumbnail_url == "http://srv/art.jpg"

    def test_empty_didl(self):
        didl = f'<DIDL-Lite xmlns="{_NS_DIDL}"></DIDL-Lite>'
        with patch("dlna.urlopen", return_value=_mock_urlopen(_soap(didl))):
            assert browse("http://fake/ctrl") == []


# ── get_control_url() ─────────────────────────────────────────────────────────

class TestGetControlUrl:
    _DEVICE_DESC = """\
<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
        <controlURL>/ctl/ContentDir</controlURL>
      </service>
    </serviceList>
  </device>
</root>"""

    def test_returns_control_url(self):
        resp = _mock_urlopen(self._DEVICE_DESC.encode())
        with patch("dlna.urlopen", return_value=resp):
            url = get_control_url("http://srv:1234/desc.xml")
        assert url == "http://srv:1234/ctl/ContentDir"

    def test_returns_none_on_network_error(self):
        with patch("dlna.urlopen", side_effect=OSError):
            assert get_control_url("http://fake/") is None

    def test_returns_none_when_no_content_directory(self):
        xml = """\
<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device><serviceList/></device>
</root>"""
        resp = _mock_urlopen(xml.encode())
        with patch("dlna.urlopen", return_value=resp):
            assert get_control_url("http://fake/") is None
