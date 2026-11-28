from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtDBus import QDBusMessage

from domain.input.gamepad_events import GamepadConnected, GamepadDisconnected
from domain.input.pointer_hiding import UncontrolledPointer
from domain.shared.event_emitter import EventEmitter
from infrastructure.gnome.input import pointer_hiding as gnome_pointer
from infrastructure.gnome.input.pointer_hiding import (
    NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES, GnomePointerHiding,
)
from infrastructure.kde.input import pointer_hiding as kde_pointer
from infrastructure.kde.input.pointer_hiding import HIDE_CURSOR_EFFECT, KwinPointerHiding
from infrastructure.linux.compositor import Compositor, build_pointer_hiding
from session import hide_idle_pointer_while_a_gamepad_drives


class FakeGamepad:
    def __init__(self):
        self.connected = EventEmitter()
        self.disconnected = EventEmitter()
        self.on_connected = self.connected.subscribe
        self.on_disconnected = self.disconnected.subscribe


class RecordingPointer(UncontrolledPointer):
    def __init__(self):
        self.calls = []

    def hide_while_idle(self):
        self.calls.append("hide")

    def keep_visible(self):
        self.calls.append("show")


class TestGamepadWiring:
    def test_pointer_hides_only_while_the_gamepad_is_connected(self):
        app, gamepad, pointer = MagicMock(), FakeGamepad(), RecordingPointer()
        hide_idle_pointer_while_a_gamepad_drives(app, gamepad, pointer)
        assert pointer.calls == []
        gamepad.connected.emit(GamepadConnected())
        gamepad.disconnected.emit(GamepadDisconnected())
        assert pointer.calls == ["hide", "show"]

    def test_pointer_is_shown_again_on_quit(self):
        app, pointer = MagicMock(), RecordingPointer()
        hide_idle_pointer_while_a_gamepad_drives(app, FakeGamepad(), pointer)
        app.aboutToQuit.connect.assert_called_once_with(pointer.keep_visible)


class TestGnomePointerHiding:
    def test_hiding_is_asked_for_by_owning_the_name(self):
        with patch.object(gnome_pointer.QDBusConnection, "sessionBus") as bus:
            GnomePointerHiding().hide_while_idle()
            GnomePointerHiding().keep_visible()
        bus.return_value.registerService.assert_called_once_with(
            NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES)
        bus.return_value.unregisterService.assert_called_once_with(
            NAME_OWNED_WHILE_THE_IDLE_POINTER_HIDES)


def _reply(value):
    reply = MagicMock()
    reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
    reply.arguments.return_value = [value]
    return reply


class FakeEffects:
    def __init__(self, loaded=False, loadable=True):
        self.loaded = loaded
        self.loadable = loadable
        self.calls = []

    def call(self, method, effect):
        assert effect == HIDE_CURSOR_EFFECT
        self.calls.append(method)
        if method == "isEffectLoaded":
            return _reply(self.loaded)
        if method == "loadEffect":
            self.loaded = self.loadable
            return _reply(self.loadable)
        self.loaded = False
        return _reply(None)


@pytest.fixture
def kwin():
    def make(**state):
        effects = FakeEffects(**state)
        with patch.object(kde_pointer, "QDBusInterface", return_value=effects):
            return KwinPointerHiding(), effects
    return make


class TestKwinPointerHiding:
    def test_loads_the_effect_and_unloads_it_again(self, kwin):
        pointer, effects = kwin()
        pointer.hide_while_idle()
        pointer.keep_visible()
        assert effects.calls == ["isEffectLoaded", "loadEffect", "unloadEffect"]

    def test_leaves_alone_an_effect_the_user_enabled(self, kwin):
        pointer, effects = kwin(loaded=True)
        pointer.hide_while_idle()
        pointer.keep_visible()
        assert effects.calls == ["isEffectLoaded"]
        assert effects.loaded

    def test_a_second_connect_does_not_ask_again(self, kwin):
        pointer, effects = kwin()
        pointer.hide_while_idle()
        pointer.hide_while_idle()
        assert effects.calls == ["isEffectLoaded", "loadEffect"]

    def test_an_effect_kwin_lacks_is_never_unloaded(self, kwin):
        pointer, effects = kwin(loadable=False)
        pointer.hide_while_idle()
        pointer.keep_visible()
        assert "unloadEffect" not in effects.calls


class TestBuilder:
    def test_gnome_hides_through_the_extension(self):
        assert isinstance(build_pointer_hiding(Compositor.GNOME), GnomePointerHiding)

    def test_kde_hides_through_kwin(self):
        with patch.object(kde_pointer, "QDBusInterface"):
            assert isinstance(build_pointer_hiding(Compositor.KDE), KwinPointerHiding)

    @pytest.mark.parametrize(
        "compositor",
        [c for c in Compositor if c not in (Compositor.GNOME, Compositor.KDE)])
    def test_the_others_leave_the_pointer_alone(self, compositor):
        assert isinstance(build_pointer_hiding(compositor), UncontrolledPointer)
