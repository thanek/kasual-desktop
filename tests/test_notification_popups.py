"""Tests for the popups adapters and their gamepad wiring."""

from unittest.mock import patch

import pytest

from domain.input.gamepad_events import GamepadConnected, GamepadDisconnected
from domain.notifications.popups import UncontrolledPopups
from domain.shared.event_emitter import EventEmitter
from infrastructure.gnome import helper
from infrastructure.gnome.notifications import popups as gnome_popups
from infrastructure.gnome.notifications.popups import (
    NAME_OWNED_WHILE_A_GAMEPAD_DRIVES, GnomeNotificationPopups,
)
from infrastructure.linux.compositor import Compositor, build_notification_popups
from session import expire_popups_while_a_gamepad_drives


class FakeGamepad:
    def __init__(self):
        self.connected = EventEmitter()
        self.disconnected = EventEmitter()
        self.on_connected = self.connected.subscribe
        self.on_disconnected = self.disconnected.subscribe


class RecordingPopups(UncontrolledPopups):
    def __init__(self):
        self.calls = []

    def expire_without_keyboard_or_mouse(self):
        self.calls.append("expire")

    def wait_for_keyboard_or_mouse(self):
        self.calls.append("wait")


class TestGamepadWiring:
    def test_popups_expire_only_while_the_gamepad_is_connected(self):
        gamepad, popups = FakeGamepad(), RecordingPopups()
        expire_popups_while_a_gamepad_drives(gamepad, popups)
        assert popups.calls == []
        gamepad.connected.emit(GamepadConnected())
        gamepad.disconnected.emit(GamepadDisconnected())
        assert popups.calls == ["expire", "wait"]


class TestGnomePopups:
    def test_gamepad_is_announced_by_owning_the_name(self):
        with patch.object(gnome_popups.QDBusConnection, "sessionBus") as bus:
            GnomeNotificationPopups().expire_without_keyboard_or_mouse()
            GnomeNotificationPopups().wait_for_keyboard_or_mouse()
        bus.return_value.registerService.assert_called_once_with(
            NAME_OWNED_WHILE_A_GAMEPAD_DRIVES)
        bus.return_value.unregisterService.assert_called_once_with(
            NAME_OWNED_WHILE_A_GAMEPAD_DRIVES)

    def test_dismissal_goes_to_the_helper_without_blocking(self):
        with patch.object(helper.QDBusConnection, "sessionBus") as bus:
            GnomeNotificationPopups().dismiss_all()
        message = bus.return_value.asyncCall.call_args.args[0]
        assert message.service() == helper.SERVICE
        assert message.member() == "DismissBanners"


class TestBuilder:
    def test_gnome_controls_its_popups(self):
        assert isinstance(
            build_notification_popups(Compositor.GNOME), GnomeNotificationPopups)

    @pytest.mark.parametrize(
        "compositor", [c for c in Compositor if c is not Compositor.GNOME])
    def test_the_others_do_not_yet(self, compositor):
        assert isinstance(build_notification_popups(compositor), UncontrolledPopups)
