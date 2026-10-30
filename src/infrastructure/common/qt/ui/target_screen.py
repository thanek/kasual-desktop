"""The screen every Kasual Desktop surface is put on — the chosen one while it
is connected, else Qt's primary, which is where the system would put it anyway."""

import weakref

from PyQt6 import sip
from PyQt6.QtGui import QGuiApplication, QScreen
from PyQt6.QtWidgets import QWidget

_aimed_at: str | None = None
_placed: "weakref.WeakSet[QWidget]" = weakref.WeakSet()


def aim_at(screen_name: str | None) -> None:
    global _aimed_at
    _aimed_at = screen_name


def target_screen() -> QScreen | None:
    chosen = next(
        (screen for screen in QGuiApplication.screens() if screen.name() == _aimed_at),
        None,
    )
    return chosen or QGuiApplication.primaryScreen()


def place_on_target_screen(widget: QWidget) -> None:
    _placed.add(widget)
    put_on(widget, target_screen())


def put_on(widget: QWidget, screen: QScreen | None) -> None:
    widget.winId()
    window = widget.windowHandle()
    if screen is not None and window is not None and window.screen() is not screen:
        window.setScreen(screen)


def narrower_than_target_screen(widget: QWidget) -> bool:
    screen = target_screen()
    return screen is not None and widget.width() < screen.geometry().width()


def placed_surfaces() -> list[QWidget]:
    return [widget for widget in _placed if not sip.isdeleted(widget)]
