"""Windows surface strategy for the shared Desktop widget.

Windows has no wlr-layer-shell, so instead of a layer-shell surface the Desktop
widget is made its OWN frameless, always-on-top (WS_EX_TOPMOST) top-level window
— the same mechanism the overlays use (see top_surface.promote_overlay_surface).
Because the widget *is* the surface, show/hide/activate/resume all operate on it
directly and uniformly, exactly like the Linux layer-shell path.

It also owns the *reactivation* trigger: when the Desktop is hidden to reveal a
launched app, there is no reliable activation event for a topmost window, so this
strategy polls the foreground window. When the Windows desktop itself
(Progman/WorkerW) comes forward — i.e. the app it ceded focus to has gone — it
fires the reactivate callback, which the Desktop routes to
``AppLifecycle.reactivate_desktop`` (idempotent).

This is the Windows half of the ``DesktopSurface`` seam; the Linux half is
``LayerShellSurface``. Together they let the whole Qt UI stay shared.
"""

import ctypes
import logging
from collections.abc import Callable

from PyQt6.QtCore import Qt, QObject, QTimer
from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Foreground window classes that mean "the bare Windows desktop is showing" —
# i.e. nothing the Desktop ceded focus to is in front any more.
_DESKTOP_WIN_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", ""})


class WindowsDesktopSurface:
    """Make the Desktop widget a frameless, topmost, fullscreen window."""

    def __init__(self) -> None:
        self._widget: QWidget | None = None
        self._restore_timer: QTimer | None = None
        self._on_reactivate: Callable[[], None] | None = None

    # ── DesktopSurface port ──────────────────────────────────────────────────

    def install(self, widget: QWidget) -> None:
        self._widget = widget
        # Frameless + Qt-managed WS_EX_TOPMOST (the flag survives show(), unlike a
        # raw SetWindowLong which Qt resets). Set before the widget is shown.
        widget.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        widget.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def show_fullscreen(self) -> None:
        self._stop_restore_monitor()
        self._widget.showFullScreen()
        self._widget.raise_()
        self._widget.activateWindow()

    def hide(self) -> None:
        # Plain hide (session disconnect / minimize): stays hidden, no auto-return.
        self._widget.hide()

    def activate(self) -> None:
        self._widget.activateWindow()

    def is_visible(self) -> bool:
        return self._widget.isVisible() if self._widget is not None else False

    def on_reactivate(self, callback: Callable[[], None]) -> None:
        self._on_reactivate = callback

    # ── Launch-hide (deferred hide when an app starts) ───────────────────────

    def hide_for_launch(self) -> None:
        """Hide to reveal a freshly launched app, and start watching so the
        Desktop returns when that app closes (the only restore signal for apps
        with no trackable process, e.g. ms-settings)."""
        self._widget.hide()
        QTimer.singleShot(1500, self._start_restore_monitor)

    # ── Foreground monitor ───────────────────────────────────────────────────

    def _start_restore_monitor(self) -> None:
        if self.is_visible() or self._restore_timer is not None:
            return
        self._restore_timer = QTimer(self._widget)
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


class TimedLaunchHide(QObject):
    """Time-based deferred hide for Windows (a ``LaunchHide``).

    The Linux ``DeferredHide`` waits for the launched app's window to map before
    hiding the Desktop. On Windows that detection is unreliable — protocol apps
    such as ``ms-settings:`` are hosted by ApplicationFrameHost and never surface
    a window we can attribute to the tile — so we hide after a short, fixed delay
    and let the surface's foreground monitor handle the return trip.
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
