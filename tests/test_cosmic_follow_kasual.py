from unittest.mock import MagicMock, patch

import pytest

from infrastructure.cosmic.wm import follow_kasual, protocol
from infrastructure.cosmic.wm.follow_kasual import CosmicWindowsFollowKasual
from infrastructure.cosmic.wm.toplevels import CosmicToplevels
from infrastructure.linux.wayland import wire
from infrastructure.linux.wayland.client import WaylandClient
from wayland_fake import FakeCompositor, pump

_GLOBALS = {
    protocol.FOREIGN_LIST: protocol.FOREIGN_LIST_VERSION,
    protocol.INFO: protocol.INFO_VERSION,
    protocol.MANAGER: protocol.MANAGER_VERSION,
    protocol.SEAT: 9,
    protocol.OUTPUT: protocol.OUTPUT_VERSION,
    protocol.WORKSPACES: protocol.WORKSPACES_VERSION,
}

KASUAL_SCREEN = "HDMI-A-1"
ELSEWHERE = 999
GROUP = 0xFF000100
WORKSPACE = 0xFF000101
FOREIGN_OPEN_BEFORE = 0xFF000000
FOREIGN_LAUNCHED = 0xFF000001


def _screen(name):
    screen = MagicMock()
    screen.name.return_value = name
    return screen


@pytest.fixture
def two_screens():
    screens = [_screen("DP-1"), _screen(KASUAL_SCREEN)]
    with patch.object(follow_kasual, "target_screen", return_value=screens[1]), \
         patch.object(follow_kasual.QGuiApplication, "screens", return_value=screens):
        yield screens


@pytest.fixture
def compositor(monkeypatch):
    fake = FakeCompositor(dict(_GLOBALS))
    fake.install(monkeypatch)
    yield fake
    fake.close()


@pytest.fixture
def client(compositor, qapp):
    connection = WaylandClient()
    connection.start()
    yield connection
    connection.close()


class World:
    def __init__(self, compositor, client, paused):
        self.compositor = compositor
        self.paused = paused
        self.follow = None
        self.toplevels = CosmicToplevels(client, self._changed)
        self.handles = {}
        assert pump(lambda: self._bound(protocol.MANAGER))

    def _changed(self):
        if self.follow is not None:
            self.follow.apply()

    def start_following(self, client):
        self.follow = CosmicWindowsFollowKasual(
            client, self.toplevels, lambda: self.paused, "kasual-desktop")
        assert pump(lambda: self._bound(protocol.WORKSPACES))
        self.kasual_output = self.compositor.bound(protocol.OUTPUT)
        self.compositor.send(self.kasual_output, protocol.OUTPUT_EVENT_NAME,
                             wire.string(KASUAL_SCREEN))
        manager = self.compositor.bound(protocol.WORKSPACES)
        self.compositor.send(manager, protocol.WORKSPACES_EVENT_GROUP, wire.new_id(GROUP))
        self.compositor.send(manager, protocol.WORKSPACES_EVENT_WORKSPACE,
                             wire.new_id(WORKSPACE))
        self.compositor.send(GROUP, protocol.GROUP_EVENT_OUTPUT_ENTER,
                             wire.object_id(self.kasual_output))
        self.compositor.send(GROUP, protocol.GROUP_EVENT_WORKSPACE_ENTER,
                             wire.object_id(WORKSPACE))
        self.compositor.send(WORKSPACE, protocol.WORKSPACE_EVENT_STATE,
                             wire.uint(protocol.WORKSPACE_STATE_ACTIVE))
        assert pump(lambda: self.follow._screens.shown_workspace_on(
            self.kasual_output) == WORKSPACE)

    def _bound(self, interface):
        try:
            self.compositor.bound(interface)
            return True
        except AssertionError:
            return False

    def announce(self, foreign, identifier, app_id="firefox"):
        listing = self.compositor.bound(protocol.FOREIGN_LIST)
        self.compositor.send(listing, protocol.LIST_EVENT_TOPLEVEL, wire.new_id(foreign))
        self.compositor.send(foreign, protocol.FOREIGN_EVENT_IDENTIFIER,
                             wire.string(identifier))
        self.compositor.send(foreign, protocol.FOREIGN_EVENT_APP_ID, wire.string(app_id))
        self.compositor.send(foreign, protocol.FOREIGN_EVENT_DONE)
        assert pump(lambda: self.toplevels.handle_for(identifier) is not None)
        self.handles[identifier] = self.toplevels.handle_for(identifier)

    def appears_on(self, identifier, output):
        self.compositor.send(self.handles[identifier], protocol.HANDLE_EVENT_OUTPUT_ENTER,
                             wire.object_id(output))
        assert pump(lambda: self._toplevel(identifier).outputs)

    def leaves(self, identifier, output):
        self.compositor.send(self.handles[identifier], protocol.HANDLE_EVENT_OUTPUT_LEAVE,
                             wire.object_id(output))
        assert pump(lambda: output not in self._toplevel(identifier).outputs)

    def goes_fullscreen(self, identifier):
        states = wire.array(int(protocol.State.FULLSCREEN).to_bytes(4, "little"))
        self.compositor.send(self.handles[identifier], protocol.HANDLE_EVENT_STATE, states)
        assert pump(lambda: self._toplevel(identifier).fullscreen)

    def _toplevel(self, identifier):
        return next(t for t in self.toplevels.toplevels() if t.identifier == identifier)

    def moves(self):
        return [request.payload for request in self.compositor.requests_to(
                    self.compositor.bound(protocol.MANAGER))
                if request.opcode == protocol.MANAGER_MOVE_TO_EXT_WORKSPACE]

    def move_of(self, identifier):
        return (wire.object_id(self.handles[identifier]) + wire.object_id(WORKSPACE)
                + wire.object_id(self.kasual_output))


@pytest.fixture
def world(compositor, client, two_screens):
    made = World(compositor, client, paused=False)
    made.start_following(client)
    return made


def test_launched_window_is_moved_to_the_kasual_screen(world):
    world.announce(FOREIGN_LAUNCHED, "launched")
    world.appears_on("launched", ELSEWHERE)
    assert pump(lambda: world.moves() == [world.move_of("launched")])


def test_window_already_on_the_kasual_screen_stays(world):
    world.announce(FOREIGN_LAUNCHED, "launched")
    world.appears_on("launched", world.kasual_output)
    assert not pump(lambda: world.moves(), timeout_s=0.2)


def test_nothing_moves_while_paused(world):
    world.paused = True
    world.announce(FOREIGN_LAUNCHED, "launched")
    world.appears_on("launched", ELSEWHERE)
    assert not pump(lambda: world.moves(), timeout_s=0.2)


def test_own_windows_are_never_moved(world):
    world.announce(FOREIGN_LAUNCHED, "launched", app_id="kasual-desktop")
    world.appears_on("launched", ELSEWHERE)
    assert not pump(lambda: world.moves(), timeout_s=0.2)


def test_going_fullscreen_elsewhere_brings_it_back(world):
    world.announce(FOREIGN_LAUNCHED, "launched")
    world.appears_on("launched", world.kasual_output)
    world.appears_on("launched", ELSEWHERE)
    world.leaves("launched", world.kasual_output)
    world.goes_fullscreen("launched")
    assert pump(lambda: world.moves() == [world.move_of("launched")])


def test_windows_open_before_are_left_where_they_are(compositor, client, two_screens):
    world = World(compositor, client, paused=False)
    world.announce(FOREIGN_OPEN_BEFORE, "before")
    world.start_following(client)
    world.appears_on("before", ELSEWHERE)
    assert not pump(lambda: world.moves(), timeout_s=0.2)
