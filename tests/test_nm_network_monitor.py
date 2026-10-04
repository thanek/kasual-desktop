import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="NetworkManager is Linux-only")

if sys.platform == "linux":
    from infrastructure.linux.network.network_manager import NMNetworkMonitor


class TestStrength:
    def test_dbus_byte_arrives_as_single_byte(self):
        assert NMNetworkMonitor._strength(b"J") == 74

    def test_plain_integer(self):
        assert NMNetworkMonitor._strength(55) == 55

    def test_missing(self):
        assert NMNetworkMonitor._strength(None) is None

    def test_empty_bytes(self):
        assert NMNetworkMonitor._strength(b"") is None
