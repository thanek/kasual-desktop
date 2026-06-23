"""Smoke + behaviour tests for NetworkOverlay (info popup + connect toggle)."""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QLabel, QPushButton

from domain.network.status import NetworkKind, NetworkStatus


def _overlay(mock_gamepad, status, *, can_reconnect=False, control=None):
    from infrastructure.common.qt.overlays.network_overlay import NetworkOverlay
    if control is None:
        control = MagicMock()
        control.can_reconnect.return_value = can_reconnect
    return NetworkOverlay(
        gamepad=mock_gamepad, status=status, control=control, feedback=MagicMock()
    )


def _texts(overlay):
    return [lbl.text() for lbl in overlay.findChildren(QLabel)]


def _button(overlay):
    return overlay.findChildren(QPushButton)[0]


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


class TestToggleButton:
    def test_online_shows_disconnect_enabled(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus(NetworkKind.WIFI, name="Dom"))
        btn = _button(ov)
        assert btn.text() == "Disconnect" and btn.isEnabled()

    def test_offline_with_history_shows_connect_enabled(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline(), can_reconnect=True)
        btn = _button(ov)
        assert btn.text() == "Connect" and btn.isEnabled()

    def test_offline_without_history_disables_button(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline(), can_reconnect=False)
        assert not _button(ov).isEnabled()

    def test_select_when_online_disconnects_and_closes(self, mock_gamepad):
        control = MagicMock()
        control.can_reconnect.return_value = False
        ov = _overlay(mock_gamepad, NetworkStatus(NetworkKind.WIFI), control=control)
        seen = []
        ov.closed.connect(lambda: seen.append(True))
        ov._handle_pad("select")
        control.disconnect.assert_called_once()
        assert seen == [True]

    def test_select_when_offline_reconnects_and_closes(self, mock_gamepad):
        control = MagicMock()
        control.can_reconnect.return_value = True
        ov = _overlay(mock_gamepad, NetworkStatus.offline(), control=control)
        ov._handle_pad("select")
        control.reconnect.assert_called_once()

    def test_select_on_disabled_button_does_nothing(self, mock_gamepad):
        control = MagicMock()
        control.can_reconnect.return_value = False
        ov = _overlay(mock_gamepad, NetworkStatus.offline(), control=control)
        seen = []
        ov.closed.connect(lambda: seen.append(True))
        ov._handle_pad("select")
        control.disconnect.assert_not_called()
        control.reconnect.assert_not_called()
        assert seen == []


class TestClosing:
    def test_cancel_closes_and_pops_handler(self, mock_gamepad):
        ov = _overlay(mock_gamepad, NetworkStatus.offline())
        seen = []
        ov.closed.connect(lambda: seen.append(True))
        ov._handle_pad("cancel")
        assert seen == [True]
        assert ov._handle_pad not in mock_gamepad._stack
