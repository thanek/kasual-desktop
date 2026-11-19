import json
import logging
import os
import tempfile

from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PyQt6.QtGui import QGuiApplication

from infrastructure.common.qt.ui.target_screen import target_screen

logger = logging.getLogger(__name__)

_KWIN_SVC = 'org.kde.KWin'
_SCRI_PATH = '/Scripting'
_SCRI_IFACE = 'org.kde.kwin.Scripting'

SERVICE = 'org.consoledesktop.KasualScreen'
PATH = '/KasualScreen'
PLUGIN = 'consoled_follow_kasual_screen'

STAY = ''

_FOLLOW_SCRIPT = """\
(function () {{
    var ownPid = {own_pid};
    var outputNamed = function (name) {{
        var outputs = workspace.screens;
        for (var i = 0; i < outputs.length; i++)
            if (outputs[i].name === name)
                return outputs[i];
        return null;
    }};
    var follow = function (w) {{
        if (!w || parseInt(w.pid) === ownPid)
            return;
        if (!(w.normalWindow || w.dialog) || w.desktopWindow || w.dock)
            return;
        callDBus({service}, {path}, '', 'targetFor', parseInt(w.pid) || 0,
                 function (name) {{
            var output = name ? outputNamed(name) : null;
            if (output && w.output !== output)
                workspace.sendClientToScreen(w, output);
        }});
    }};
    var track = function (w) {{
        w.fullScreenChanged.connect(function () {{
            if (w.fullScreen)
                follow(w);
        }});
    }};
    var existing = workspace.windowList();
    for (var i = 0; i < existing.length; i++)
        track(existing[i]);
    workspace.windowAdded.connect(function (w) {{
        track(w);
        follow(w);
    }});
}})();
"""


def follow_script(own_pid: int) -> str:
    return _FOLLOW_SCRIPT.format(
        service=json.dumps(SERVICE), path=json.dumps(PATH), own_pid=own_pid)


class KdeWindowsFollowKasual(QObject):
    def __init__(self, paused: Callable[[], bool]) -> None:
        super().__init__()
        self._paused = paused
        self._scripting = QDBusInterface(
            _KWIN_SVC, _SCRI_PATH, _SCRI_IFACE, QDBusConnection.sessionBus())
        self._path: str | None = None
        self._registered = False

    @pyqtSlot(int, result=str)
    def targetFor(self, pid: int) -> str:
        if pid == os.getpid() or self._paused() or len(QGuiApplication.screens()) < 2:
            return STAY
        screen = target_screen()
        return screen.name() if screen is not None else STAY

    def start(self) -> None:
        self._unload_any_copy_left_by_a_crash()
        bus = QDBusConnection.sessionBus()
        self._registered = (
            bus.registerObject(PATH, self, QDBusConnection.RegisterOption.ExportAllSlots)
            and bus.registerService(SERVICE))
        if not self._registered:
            logger.warning('KWin: cannot export %s; launched apps stay where KWin puts them',
                           SERVICE)
            bus.unregisterObject(PATH)
            return
        path = self._write(follow_script(os.getpid()))
        if path is None:
            return
        reply = self._scripting.call('loadScript', path, PLUGIN)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            logger.warning('KWin: cannot keep launched apps on Kasual screen: %s',
                           reply.errorMessage())
            self._unlink(path)
            return
        self._scripting.call('start')
        self._path = path
        logger.info('KWin: windows follow Kasual Desktop to its screen')

    def stop(self) -> None:
        self._scripting.call('unloadScript', PLUGIN)
        if self._path is not None:
            self._unlink(self._path)
            self._path = None
        if self._registered:
            bus = QDBusConnection.sessionBus()
            bus.unregisterService(SERVICE)
            bus.unregisterObject(PATH)
            self._registered = False

    def _unload_any_copy_left_by_a_crash(self) -> None:
        self._scripting.call('unloadScript', PLUGIN)

    def _write(self, content: str) -> str | None:
        try:
            fd, path = tempfile.mkstemp(suffix='.js', prefix='consoled_')
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            return path
        except OSError as exc:
            logger.error('Could not save KWin script: %s', exc)
            return None

    def _unlink(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError as exc:
            logger.debug('Script cleanup failed (%s): %s', path, exc)
