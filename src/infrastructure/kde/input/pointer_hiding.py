import logging

from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from domain.input.pointer_hiding import PointerHiding

logger = logging.getLogger(__name__)

_KWIN_SVC = "org.kde.KWin"
_EFFECTS_PATH = "/Effects"
_EFFECTS_IFACE = "org.kde.kwin.Effects"
HIDE_CURSOR_EFFECT = "hidecursor"


def _answer(reply: QDBusMessage) -> bool:
    return reply.type() == QDBusMessage.MessageType.ReplyMessage and bool(reply.arguments()[0])


class KwinPointerHiding(PointerHiding):
    def __init__(self) -> None:
        self._effects = QDBusInterface(
            _KWIN_SVC, _EFFECTS_PATH, _EFFECTS_IFACE, QDBusConnection.sessionBus())
        self._loaded_by_us = False

    def hide_while_idle(self) -> None:
        if self._loaded_by_us or self._loaded():
            return
        self._loaded_by_us = _answer(self._effects.call("loadEffect", HIDE_CURSOR_EFFECT))
        if not self._loaded_by_us:
            logger.warning("KWin: cannot load the %s effect; the idle pointer stays on screen",
                           HIDE_CURSOR_EFFECT)

    def keep_visible(self) -> None:
        if not self._loaded_by_us:
            return
        self._effects.call("unloadEffect", HIDE_CURSOR_EFFECT)
        self._loaded_by_us = False

    def _loaded(self) -> bool:
        return _answer(self._effects.call("isEffectLoaded", HIDE_CURSOR_EFFECT))
