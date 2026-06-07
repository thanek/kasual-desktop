"""Deferred hide of the Desktop until a freshly launched app's window is mapped."""

import os
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer

from domain.app import App
from system.app_manager import AppManager
from system.window_manager import KWinWindowManager, expand_pid_tree

_POLL_INTERVAL_MS = 150
_GUARD_TIMEOUT_MS = 5000


class DeferredHide(QObject):
    """Hide the Desktop only once a launched app actually has a mapped window.

    The Desktop is a top-layer surface sitting above windowed apps, so it must
    hide for a launched app to be visible. Hiding the instant we launch would
    expose the DE desktop underneath until the app draws its first frame; instead
    we keep the Desktop up and hide it when KWin first reports a window belonging
    to the app, polling the window list quickly meanwhile. A safety guard hides
    anyway so a slow or undetected window never strands us in front of the app.

    Lifecycle: ``arm(idx)`` after a successful launch, ``cancel()`` if the launch
    fails or the app exits before its window ever maps.
    """

    def __init__(
        self,
        wm:          KWinWindowManager,
        app_manager: AppManager,
        apps:        list[App],
        on_hide:     Callable[[], None],
        parent:      QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._wm          = wm
        self._app_manager = app_manager
        self._apps        = apps
        self._on_hide     = on_hide

        self._idx:      int | None = None
        self._grace_ms: int        = 0

        # Poll the window list quickly while waiting for the app's window.
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._wm.refresh_now)
        # Safety timeout: hide anyway if no window is ever detected.
        self._guard = QTimer(self)
        self._guard.setSingleShot(True)
        self._guard.timeout.connect(self._force)
        # Optional settle delay after the first window maps (e.g. Steam bootstrap
        # window vs. Big Picture) so we don't uncover a half-drawn frame.
        self._grace = QTimer(self)
        self._grace.setSingleShot(True)
        self._grace.timeout.connect(self._hide_now)

    # ── API ──────────────────────────────────────────────────────────────────

    @property
    def is_armed(self) -> bool:
        return self._idx is not None

    def arm(self, idx: int) -> None:
        """Start watching for app *idx*'s window; hide the Desktop once it maps."""
        self.cancel()
        self._idx = idx
        self._grace_ms = self._apps[idx].launch_hide_grace_ms
        self._wm.windows_updated.connect(self._on_windows)
        self._poll.start()
        self._guard.start(_GUARD_TIMEOUT_MS)
        self._wm.refresh_now()

    def cancel(self) -> None:
        """Tear the watcher down without hiding the Desktop."""
        if self._idx is None:
            return
        self._idx = None
        self._stop_watch()
        self._grace.stop()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_windows(self, windows: list[dict]) -> None:
        idx = self._idx
        if idx is None or not self._app_window_present(idx, windows):
            return
        self._stop_watch()
        if self._grace_ms > 0:
            self._grace.start(self._grace_ms)
        else:
            self._hide_now()

    def _app_window_present(self, idx: int, windows: list[dict]) -> bool:
        """True if `windows` contains a window belonging to launched app `idx`.

        Matched by PID subtree (covers normal child windows), with a resource /
        desktop-file fallback for forwarder launchers like `steam steam://...`
        whose visible window runs under an unrelated PID.
        """
        pid  = self._app_manager.running_pid(idx)
        pids = expand_pid_tree({pid}) if pid else set()
        cmd  = self._apps[idx].command_basename
        for w in windows:
            wpid = w.get('pid')
            if wpid and wpid in pids:
                return True
            rc = w.get('resourceClass', '').lower()
            df = os.path.splitext(w.get('desktopFile', '').lower())[0]
            if cmd and (rc == cmd or df == cmd):
                return True
        return False

    def _force(self) -> None:
        """Safety-timeout path: hide even if no window was detected."""
        self._stop_watch()
        self._hide_now()

    def _hide_now(self) -> None:
        self._idx = None
        self._on_hide()

    def _stop_watch(self) -> None:
        """Stop the poll/guard and disconnect (keeps a queued grace hide)."""
        self._poll.stop()
        self._guard.stop()
        try:
            self._wm.windows_updated.disconnect(self._on_windows)
        except TypeError:
            pass
