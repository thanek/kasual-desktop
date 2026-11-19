import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="KWin adapter")

from PyQt6.QtDBus import QDBusMessage  # noqa: E402

from infrastructure.kde.display import follow_kasual  # noqa: E402
from infrastructure.kde.display.follow_kasual import (  # noqa: E402
    PLUGIN, SERVICE, STAY, KdeWindowsFollowKasual, follow_script,
)


def _screen(name):
    screen = MagicMock()
    screen.name.return_value = name
    return screen


@pytest.fixture
def scripting():
    iface = MagicMock()
    reply = MagicMock()
    reply.type.return_value = QDBusMessage.MessageType.ReplyMessage
    iface.call.return_value = reply
    with patch.object(follow_kasual, "QDBusInterface", return_value=iface):
        yield iface


@pytest.fixture
def two_screens():
    screens = [_screen('DP-1'), _screen('HDMI-A-1')]
    with patch.object(follow_kasual, "target_screen", return_value=screens[1]), \
         patch.object(follow_kasual.QGuiApplication, "screens", return_value=screens):
        yield screens


def test_script_asks_us_on_new_and_fullscreened_windows():
    script = follow_script(4242)
    assert 'var ownPid = 4242;' in script
    assert f'callDBus("{SERVICE}"' in script
    assert 'workspace.windowAdded.connect' in script
    assert 'w.fullScreenChanged.connect' in script
    assert 'workspace.sendClientToScreen(w, output)' in script


def test_names_kasual_screen_while_unpaused(scripting, two_screens):
    follow = KdeWindowsFollowKasual(paused=lambda: False)
    assert follow.targetFor(1234) == 'HDMI-A-1'


def test_leaves_windows_alone_while_paused(scripting, two_screens):
    follow = KdeWindowsFollowKasual(paused=lambda: True)
    assert follow.targetFor(1234) == STAY


def test_never_moves_our_own_surfaces(scripting, two_screens):
    follow = KdeWindowsFollowKasual(paused=lambda: False)
    assert follow.targetFor(os.getpid()) == STAY


def test_nothing_to_follow_with_a_single_screen(scripting):
    only = [_screen('DP-1')]
    with patch.object(follow_kasual, "target_screen", return_value=only[0]), \
         patch.object(follow_kasual.QGuiApplication, "screens", return_value=only):
        assert KdeWindowsFollowKasual(paused=lambda: False).targetFor(1234) == STAY


def test_start_loads_the_script_and_stop_unloads_it(scripting):
    bus = MagicMock()
    bus.registerObject.return_value = True
    bus.registerService.return_value = True
    with patch.object(follow_kasual.QDBusConnection, "sessionBus", return_value=bus):
        follow = KdeWindowsFollowKasual(paused=lambda: False)
        follow.start()
        follow.stop()
    methods = [c.args[0] for c in scripting.call.call_args_list]
    assert methods == ['unloadScript', 'loadScript', 'start', 'unloadScript']
    assert scripting.call.call_args_list[1].args[2] == PLUGIN
    bus.unregisterService.assert_called_with(SERVICE)
