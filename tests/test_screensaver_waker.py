"""Testy wygaszacza — throttling poke, inhibicja przy widocznym KD, adresy D-Bus
i dobór per kompozytor."""

from unittest.mock import MagicMock, patch

import pytest

from PyQt6.QtDBus import QDBusMessage
from PyQt6.QtWidgets import QWidget

from infrastructure.linux.compositor import build_screensaver_waker
from infrastructure.linux.display import screensaver
from infrastructure.linux.display.screensaver import (
    ScreenSaverInhibitor, ScreenSaverWaker, VisibilityInhibitor,
    freedesktop_activity_message, inhibit_message,
)

_ENV_VARS = (
    "KDE_FULL_SESSION",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_DESKTOP",
    "SWAYSOCK",
    "HYPRLAND_INSTANCE_SIGNATURE",
)


@pytest.fixture
def clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestThrottle:
    def test_first_poke_sends(self):
        send = MagicMock()
        ScreenSaverWaker(send).poke()
        send.assert_called_once()

    def test_poke_within_window_is_dropped(self):
        send = MagicMock()
        waker = ScreenSaverWaker(send)
        with patch.object(screensaver.time, "monotonic", side_effect=[0.0, 1.0]):
            waker.poke()
            waker.poke()
        send.assert_called_once()

    def test_poke_after_window_sends_again(self):
        send = MagicMock()
        waker = ScreenSaverWaker(send)
        after = screensaver.THROTTLE_SECONDS + 1.0
        with patch.object(screensaver.time, "monotonic", side_effect=[0.0, after]):
            waker.poke()
            waker.poke()
        assert send.call_count == 2


class TestMessages:
    def test_freedesktop_message(self):
        msg = freedesktop_activity_message()
        assert msg.service() == "org.freedesktop.ScreenSaver"
        assert msg.path() == "/org/freedesktop/ScreenSaver"
        assert msg.interface() == "org.freedesktop.ScreenSaver"
        assert msg.member() == "SimulateUserActivity"

    def test_gnome_helper_call(self):
        from infrastructure.gnome import helper
        with patch.object(helper.QDBusConnection, "sessionBus") as bus:
            helper.simulate_user_activity()
        msg = bus.return_value.asyncCall.call_args.args[0]
        assert msg.service() == helper.SERVICE
        assert msg.path() == helper.OBJECT_PATH
        assert msg.member() == "SimulateUserActivity"


def _bus_with_inhibit_reply(cookie):
    bus = MagicMock()
    reply = bus.call.return_value
    reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
    reply.arguments.return_value = [cookie]
    return bus


class TestInhibitor:
    def test_inhibit_message(self):
        msg = inhibit_message()
        assert msg.service() == "org.freedesktop.ScreenSaver"
        assert msg.member() == "Inhibit"
        assert msg.arguments() == ["Kasual Desktop", "Gamepad UI is on screen"]

    def test_release_sends_uninhibit_with_cookie(self):
        bus = _bus_with_inhibit_reply(7)
        with patch.object(screensaver.QDBusConnection, "sessionBus", return_value=bus):
            inhibitor = ScreenSaverInhibitor()
            inhibitor.inhibit()
            inhibitor.release()
        msg = bus.asyncCall.call_args.args[0]
        assert msg.member() == "UnInhibit"

    def test_second_inhibit_is_a_noop(self):
        bus = _bus_with_inhibit_reply(7)
        with patch.object(screensaver.QDBusConnection, "sessionBus", return_value=bus):
            inhibitor = ScreenSaverInhibitor()
            inhibitor.inhibit()
            inhibitor.inhibit()
        assert bus.call.call_count == 1

    def test_release_without_cookie_is_a_noop(self):
        bus = MagicMock()
        with patch.object(screensaver.QDBusConnection, "sessionBus", return_value=bus):
            ScreenSaverInhibitor().release()
        bus.asyncCall.assert_not_called()

    def test_failed_inhibit_leaves_no_cookie(self):
        bus = MagicMock()
        bus.call.return_value.type.return_value = QDBusMessage.MessageType.ErrorMessage
        with patch.object(screensaver.QDBusConnection, "sessionBus", return_value=bus):
            inhibitor = ScreenSaverInhibitor()
            inhibitor.inhibit()
            inhibitor.release()
        bus.asyncCall.assert_not_called()

    def test_release_is_idempotent(self):
        bus = _bus_with_inhibit_reply(7)
        with patch.object(screensaver.QDBusConnection, "sessionBus", return_value=bus):
            inhibitor = ScreenSaverInhibitor()
            inhibitor.inhibit()
            inhibitor.release()
            inhibitor.release()
        assert bus.asyncCall.call_count == 1


class TestVisibilityInhibitor:
    def test_show_inhibits_and_hide_releases(self, qapp):
        inhibitor = MagicMock()
        widget = QWidget()
        VisibilityInhibitor(inhibitor, parent=widget).watch(widget)
        widget.show()
        inhibitor.inhibit.assert_called()
        inhibitor.release.assert_not_called()
        widget.hide()
        inhibitor.release.assert_called()


class TestBuilder:
    def test_gnome_uses_helper(self, clean_env):
        clean_env.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        from infrastructure.gnome.helper import simulate_user_activity
        assert build_screensaver_waker()._send is simulate_user_activity

    def test_kde_uses_freedesktop(self, clean_env):
        clean_env.setenv("KDE_FULL_SESSION", "true")
        assert build_screensaver_waker()._send is screensaver.simulate_freedesktop_activity

    def test_unknown_falls_back_to_freedesktop(self, clean_env):
        assert build_screensaver_waker()._send is screensaver.simulate_freedesktop_activity
