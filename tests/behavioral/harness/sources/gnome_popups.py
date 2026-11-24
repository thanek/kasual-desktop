"""PopupSource for GNOME: the banners of the Shell's message tray."""

import json
import time

from PyQt6.QtDBus import QDBusConnection, QDBusMessage

_HELPER = ('org.consoledesktop.GnomeHelper', '/org/consoledesktop/GnomeHelper',
           'org.consoledesktop.GnomeHelper')
_IDLE_MONITOR = ('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core',
                 'org.gnome.Mutter.IdleMonitor')


def _call(target: tuple[str, str, str], method: str) -> QDBusMessage:
    return QDBusConnection.sessionBus().call(QDBusMessage.createMethodCall(*target, method))


def _answer(target: tuple[str, str, str], method: str):
    reply = _call(target, method)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        raise RuntimeError(f'{target[0]}.{method}: {reply.errorMessage()}')
    return reply.arguments()[0]


class GnomePopupSource:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def is_available(self) -> bool:
        try:
            return 'banners' in json.loads(_answer(_HELPER, 'Debug'))
        except RuntimeError:
            return False

    def shown(self) -> str | None:
        return self._banners()['shown']

    def queued(self) -> list[str]:
        return self._banners()['queued']

    def keyboard_and_mouse_idle_s(self) -> float:
        return _answer(_IDLE_MONITOR, 'GetIdletime') / 1000

    def _banners(self) -> dict:
        banners = json.loads(_answer(_HELPER, 'Debug'))['banners']
        self.history.append({'at': time.time(), **banners})
        return banners
