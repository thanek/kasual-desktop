"""Windows surface strategy for the shared Desktop widget.

Windows has no wlr-layer-shell, so the Desktop can't keep itself above other
windows as its own top-level. Instead it is hosted inside a separate
WS_EX_TOPMOST window (``WindowsShellManager`` / ``ShellWindow``) and the surface
operations the Desktop drives — show fullscreen, hide, activate — are forwarded
to that host.

It also owns the *reactivation* trigger: when the Desktop is hidden behind a
launched app, there is no Wayland-style ActivationChange we can rely on for a
window hosted under a topmost shell, so this strategy polls the foreground
window. When the Windows desktop itself (Progman/WorkerW) comes forward — i.e.
the app the Desktop ceded focus to has gone — it fires the reactivate callback,
which the Desktop routes to ``AppLifecycle.reactivate_desktop`` (idempotent).

This is the Windows half of the ``DesktopSurface`` seam; the Linux half is
``LayerShellSurface``. Together they let the whole Qt UI stay shared.
"""

import ctypes
import logging
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class TimedLaunchHide(QObject):
    """Time-based deferred hide for Windows (a ``LaunchHide``).

    The Linux ``DeferredHide`` waits for the launched app's window to map before
    hiding the Desktop. On Windows that detection is unreliable — protocol apps
    such as ``ms-settings:`` are hosted by ApplicationFrameHost and never surface
    a window we can attribute to the tile — so we simply hide after a short, fixed
    delay and let the foreground monitor handle the return trip.
    """

    def __init__(self, on_hide: Callable[[], None], delay_ms: int = 500,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_hide = on_hide
        self._delay_ms = delay_ms
        self._timer: QTimer | None = None

    @property
    def is_armed(self) -> bool:
        return self._timer is not None

    def arm(self, idx: int) -> None:
        self.cancel()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._timer.start(self._delay_ms)

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    def _fire(self) -> None:
        self.cancel()
        self._on_hide()

# Foreground window classes that mean "the bare Windows desktop is showing" —
# i.e. nothing the Desktop ceded focus to is in front any more.
_DESKTOP_WIN_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", ""})


class WindowsHostSurface:
    """Host the Desktop widget inside a topmost shell window and drive it there."""

    def __init__(self, shell_manager) -> None:
        self._shell_manager = shell_manager
        self._host: QWidget | None = None
        self._widget: QWidget | None = None
        self._restore_timer: QTimer | None = None
        self._on_reactivate: Callable[[], None] | None = None

    # ── DesktopSurface port ──────────────────────────────────────────────────

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        # Create the WS_EX_TOPMOST host (already shown fullscreen) and parent the
        # Desktop into it. The Desktop builds its own layout/children afterwards.
        self._host = self._shell_manager.install()
        layout = QVBoxLayout(self._host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)

    def show_fullscreen(self) -> None:
        self._stop_restore_monitor()
        if self._host is not None:
            self._host.showFullScreen()
            self._host.raise_()
            self._host.activateWindow()
        else:
            self._widget.showFullScreen()

    def hide(self) -> None:
        if self._host is not None:
            self._host.hide()
        else:
            self._widget.hide()
        # Apps take a moment to map and grab focus; wait before watching for the
        # bare desktop so we don't immediately bounce back over a launching app.
        QTimer.singleShot(1500, self._start_restore_monitor)

    def activate(self) -> None:
        if self._host is not None:
            self._host.activateWindow()
        else:
            self._widget.activateWindow()

    def is_visible(self) -> bool:
        target = self._host if self._host is not None else self._widget
        return target.isVisible() if target is not None else False

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        self._on_reactivate = callback

    # ── Public ───────────────────────────────────────────────────────────────

    @property
    def host(self) -> QWidget | None:
        """The topmost shell window hosting the Desktop (for ESC/desktop-shell wiring)."""
        return self._host

    # ── Foreground monitor (restore the Desktop when the app closes) ─────────

    def _start_restore_monitor(self) -> None:
        if self.is_visible() or self._restore_timer is not None:
            return
        self._restore_timer = QTimer(self._host)
        self._restore_timer.timeout.connect(self._check_foreground)
        self._restore_timer.start(600)

    def _stop_restore_monitor(self) -> None:
        if self._restore_timer is not None:
            self._restore_timer.stop()
            self._restore_timer.deleteLater()
            self._restore_timer = None

    def _check_foreground(self) -> None:
        if self.is_visible():
            self._stop_restore_monitor()
            return
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            win_class = buf.value
        else:
            win_class = ""
        if win_class in _DESKTOP_WIN_CLASSES:
            self._stop_restore_monitor()
            if self._on_reactivate is not None:
                self._on_reactivate()
