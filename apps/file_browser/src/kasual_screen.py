import os

from PyQt6.QtWidgets import QApplication, QWidget

KASUAL_SCREEN_ENV = "KD_SCREEN"


def show_fullscreen_where_kasual_is(window: QWidget) -> None:
    named = os.environ.get(KASUAL_SCREEN_ENV)
    screen = next((s for s in QApplication.screens() if s.name() == named), None)
    if screen is not None:
        window.winId()
        window.windowHandle().setScreen(screen)
    window.showFullScreen()
