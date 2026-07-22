"""Drive a relayout on display-configuration changes.

Qt emits these signals application-wide regardless of whether the Desktop is
mapped, so a resolution change made while it is minimized is caught here — a poll
would only catch it after the surface is already back on screen the wrong size.
"""

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QGuiApplication, QScreen

# Several signals fire for a single reconfiguration (primary swap + geometry +
# DPI); coalesce them into one relayout.
_COALESCE_MS = 150


class ScreenWatcher(QObject):
    def __init__(self, on_changed: Callable[[], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self._bound: list[QScreen] = []

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_COALESCE_MS)
        self._debounce.timeout.connect(self._on_changed)

        app = QGuiApplication.instance()
        app.primaryScreenChanged.connect(self._schedule)
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        self._bind_screens()

    def _on_screens_changed(self, _screen: QScreen) -> None:
        self._bind_screens()
        self._schedule()

    def _bind_screens(self) -> None:
        for screen in self._bound:
            screen.geometryChanged.disconnect(self._schedule)
            screen.logicalDotsPerInchChanged.disconnect(self._schedule)
        self._bound = list(QGuiApplication.screens())
        for screen in self._bound:
            screen.geometryChanged.connect(self._schedule)
            screen.logicalDotsPerInchChanged.connect(self._schedule)

    def _schedule(self, *_args) -> None:
        self._debounce.start()
