"""Tests for the network presentation helpers (icon + popup rows)."""

from domain.network.status import NetworkKind, NetworkStatus
from domain.network.view import connect_button, icon_for, info_lines, title


class TestIconFor:
    def test_each_kind_has_an_icon(self):
        assert icon_for(NetworkKind.WIFI) == "fa5s.wifi"
        assert icon_for(NetworkKind.ETHERNET) == "fa5s.network-wired"
        assert icon_for(NetworkKind.OFFLINE) == "mdi.wifi-off"
        assert icon_for(NetworkKind.UNKNOWN) == "fa5s.globe"


class TestInfoLines:
    def test_offline_is_a_single_status_line(self):
        rows = info_lines(NetworkStatus.offline())
        assert rows == [("Status", "Not connected")]

    def test_wifi_full_details(self):
        s = NetworkStatus(NetworkKind.WIFI, name="Dom", interface="wlan0",
                          ip_address="192.168.1.5", signal=66)
        d = dict(info_lines(s))
        assert d["Type"] == "Wi-Fi"
        assert d["Network"] == "Dom"
        assert d["Signal"] == "66%"
        assert d["IP address"] == "192.168.1.5"
        assert d["Interface"] == "wlan0"

    def test_omits_empty_fields(self):
        s = NetworkStatus(NetworkKind.ETHERNET, name="Wired", interface="eth0")
        labels = [label for label, _ in info_lines(s)]
        assert "Signal" not in labels       # no Wi-Fi signal
        assert "IP address" not in labels    # not resolved
        assert "Type" in labels and "Interface" in labels

    def test_ethernet_uses_connection_label(self):
        s = NetworkStatus(NetworkKind.ETHERNET, name="Wired 1")
        assert ("Connection", "Wired 1") in info_lines(s)


def test_title():
    assert title() == "Network"


class TestConnectButton:
    def test_online_offers_disconnect(self):
        b = connect_button(NetworkStatus(NetworkKind.WIFI, name="Dom"), can_reconnect=False)
        assert b.label == "Disconnect"
        assert b.reconnect is False
        assert b.enabled is True

    def test_offline_with_history_offers_enabled_connect(self):
        b = connect_button(NetworkStatus.offline(), can_reconnect=True)
        assert b.label == "Connect"
        assert b.reconnect is True
        assert b.enabled is True

    def test_offline_without_history_disables_connect(self):
        b = connect_button(NetworkStatus.offline(), can_reconnect=False)
        assert b.label == "Connect"
        assert b.enabled is False
