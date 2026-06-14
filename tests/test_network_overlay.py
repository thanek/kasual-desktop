"""Smoke + behaviour tests for NetworkOverlay (read-only info popup)."""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QLabel

from domain.network.status import NetworkKind, NetworkStatus


def _overlay(mock_gamepad, status):
    from infrastructure.qt.overlays.network_overlay import NetworkOverlay
    return NetworkOverlay(gamepad=mock_gamepad, status=status, feedback=MagicMock())


def _texts(overlay):
    return [lbl.text() for lbl in overlay.findChildren(QLabel)]


class TestRender:
    def test_shows_detail_values(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus(
            NetworkKind.WIFI, name="Dom", interface="wlan0", signal=66))
        t = _texts(ov)
        assert "Dom" in t and "66%" in t and "wlan0" in t

    def test_offline_shows_not_connected(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline())
        assert "Not connected" in _texts(ov)

    def test_registers_handler(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline())
        assert ov._handle_pad in mock_gamepad._stack


class TestClosing:
    def test_cancel_closes_and_pops_handler(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline())
        seen = []
        ov.closed.connect(lambda: seen.append(True))
        ov._handle_pad("cancel")
        assert seen == [True]
        assert ov._handle_pad not in mock_gamepad._stack

    def test_select_also_closes(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline())
        seen = []
        ov.closed.connect(lambda: seen.append(True))
        ov._handle_pad("select")
        assert seen == [True]
