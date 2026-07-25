"""Deferred return of the Desktop once a launched app's last window unmaps."""

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from domain.catalog.app import App
from domain.catalog.window import Window
from domain.lifecycle.launch_show import LaunchShow
from domain.lifecycle.process_manager import ProcessManager
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import Unsubscribe
from infrastructure.common.qt._meta import ProtocolQtMeta
from infrastructure.linux.qt.desktop.app_windows import has_mapped_window

_POLL_INTERVAL_MS = 150
_CONFIRM_MS = 500


class DeferredShow(QObject, LaunchShow, metaclass=ProtocolQtMeta):
    """Take the screen back when a launched app drops its last window, rather
    than when its process exits.

    Steam keeps its process alive 1–5 s after Big Picture closes. Waiting for the
    exit leaves the parked Desktop uncovered under the DE's panels and any
    leftover windows for that whole stretch.

    A window that unmaps only to map again — an app switching video mode — would
    bounce the Desktop over a running app, so a window-less list must hold for
    ``_CONFIRM_MS`` before it counts.

    Lifecycle: ``arm(app)`` when the Desktop cedes the screen to *app*,
    ``cancel()`` once it is back in front by any other route.
    """

    def __init__(
        self,
        wm:          WindowManager,
        app_manager: ProcessManager,
        on_show:     Callable[[], None],
        parent:      QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._wm          = wm
        self._app_manager = app_manager
        self._on_show     = on_show

        self._app:   App | None         = None
        self._unsub: Unsubscribe | None = None
        # Nothing to return from until the app has actually shown a window: a
        # launch that has not drawn yet is window-less too.
        self._seen_window = False

        self._poll = QTimer(self)   # refreshes the window list while confirming
        self._poll.setInterval(_POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._wm.refresh_now)
        self._confirm = QTimer(self)
        self._confirm.setSingleShot(True)
        self._confirm.setInterval(_CONFIRM_MS)
        self._confirm.timeout.connect(self._show_now)

    # ── API ──────────────────────────────────────────────────────────────────

    @property
    def is_armed(self) -> bool:
        return self._app is not None

    @property
    def has_seen_window(self) -> bool:
        return self._seen_window

    def arm(self, app: App) -> None:
        """Start watching *app*'s windows; show the Desktop once they are gone."""
        self.cancel()
        self._app = app
        self._seen_window = False
        self._unsub = self._wm.on_windows_updated(self._on_windows)

    def cancel(self) -> None:
        """Tear the watcher down without showing the Desktop."""
        if self._app is None:
            return
        self._app = None
        self._stop_watch()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_windows(self, windows: list[Window]) -> None:
        app = self._app
        if app is None:
            return
        if has_mapped_window(app, windows, self._app_manager):
            self._seen_window = True
            self._stop_confirm()
        elif self._seen_window and not self._confirm.isActive():
            self._confirm.start()
            self._poll.start()

    def _show_now(self) -> None:
        self._app = None
        self._stop_watch()
        self._on_show()

    def _stop_confirm(self) -> None:
        self._confirm.stop()
        self._poll.stop()

    def _stop_watch(self) -> None:
        self._stop_confirm()
        if self._unsub is not None:
            self._unsub()
            self._unsub = None