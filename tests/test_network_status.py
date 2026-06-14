"""Tests for the NetworkStatus value object."""

from domain.network.status import NetworkKind, NetworkStatus


class TestNetworkStatus:
    def test_offline_factory(self):
        s = NetworkStatus.offline()
        assert s.kind is NetworkKind.OFFLINE
        assert s.online is False

    def test_online_when_not_offline(self):
        for kind in (NetworkKind.WIFI, NetworkKind.ETHERNET, NetworkKind.UNKNOWN):
            assert NetworkStatus(kind).online is True

    def test_detail_fields_optional(self):
        s = NetworkStatus(NetworkKind.ETHERNET)
        assert s.name == "" and s.interface == ""
        assert s.ip_address is None and s.signal is None

    def test_equality_drives_change_detection(self):
        a = NetworkStatus(NetworkKind.WIFI, name="Dom", signal=70)
        b = NetworkStatus(NetworkKind.WIFI, name="Dom", signal=70)
        c = NetworkStatus(NetworkKind.WIFI, name="Dom", signal=71)
        assert a == b
        assert a != c
