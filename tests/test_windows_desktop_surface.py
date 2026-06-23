"""Tests for WindowsDesktopSurface and TimedLaunchHide.

Covers:

  - ``WindowsDesktopSurface.install``: sets FramelessWindowHint + WindowStaysOnTopHint.
  - ``show_fullscreen``/``hide``/``activate``/``is_visible``/``on_reactivate``
    delegates to the widget.
  - ``hide_for_launch``: hides the widget and starts the restore monitor after
    1500 ms (``QTimer.singleShot``).
  - ``_check_foreground``: foreground class in ``_DESKTOP_WIN_CLASSES`` →
    stop monitor + callback; other class → noop; widget already visible → stop
    without callback.
  - ``TimedLaunchHide``: arm/cancel/is_armed/_fire; arm-after-arm resets the
    timer.

Skipped on non-Windows: ``ctypes.windll.user32`` is Windows-only.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from infrastructure.windows.qt.desktop_surface import (
    _DESKTOP_WIN_CLASSES, WindowsDesktopSurface, TimedLaunchHide,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_surface(widget=None, visible=False):
    surface = WindowsDesktopSurface()
    if widget is not None:
        surface.install(widget)
    else:
        w = MagicMock()
        w.isVisible.return_value = visible
        surface.install(w)
    return surface


# ── install ───────────────────────────────────────────────────────────────────

class TestInstall:
    def test_sets_frameless_and_topmost_hints(self, qapp):
        widget = QWidget()
        surface = WindowsDesktopSurface()
        surface.install(widget)
        assert widget.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert surface._widget is widget

    def test_stores_widget(self, qapp):
        widget = QWidget()
        surface = WindowsDesktopSurface()
        surface.install(widget)
        assert surface._widget is widget


# ── show_fullscreen ───────────────────────────────────────────────────────────

class TestShowFullscreen:
    def test_shows_and_raises_widget(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface.show_fullscreen()
        widget.showFullScreen.assert_called_once()
        widget.raise_.assert_called_once()
        widget.activateWindow.assert_called_once()

    def test_stops_restore_monitor(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface._restore_timer = MagicMock()
        surface.show_fullscreen()
        surface._restore_timer.stop.assert_called_once()


# ── hide / activate / is_visible / on_reactivate ──────────────────────────────

class TestHide:
    def test_hides_widget(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface.hide()
        widget.hide.assert_called_once()


class TestActivate:
    def test_activates_widget(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface.activate()
        widget.activateWindow.assert_called_once()


class TestIsVisible:
    def test_returns_false_when_no_widget(self):
        assert WindowsDesktopSurface().is_visible() is False

    def test_delegates_to_widget(self, qapp):
        widget = QWidget()
        surface = WindowsDesktopSurface()
        surface.install(widget)
        assert surface.is_visible() is False
        widget.show()
        assert surface.is_visible() is True


class TestOnReactivate:
    def test_stores_callback(self, qapp):
        cb = lambda: None
        surface = WindowsDesktopSurface()
        surface.on_reactivate(cb)
        assert surface._on_reactivate is cb


# ── hide_for_launch ───────────────────────────────────────────────────────────

class TestHideForLaunch:
    def test_hides_widget(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        with patch("infrastructure.windows.qt.desktop_surface.QTimer.singleShot"):
            surface.hide_for_launch()
        widget.hide.assert_called_once()

    def test_schedules_restore_monitor_after_1500ms(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        with patch("infrastructure.windows.qt.desktop_surface.QTimer.singleShot") as ss:
            surface.hide_for_launch()
        ss.assert_called_once_with(1500, surface._start_restore_monitor)


# ── _start_restore_monitor / _stop_restore_monitor ────────────────────────────

class TestStartRestoreMonitor:
    def test_creates_qtimer_with_600ms(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface._start_restore_monitor()
        assert surface._restore_timer is not None
        assert surface._restore_timer.interval() == 600

    def test_connects_timeout_to_check_foreground(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface._start_restore_monitor()
        assert surface._restore_timer.receivers(
            surface._restore_timer.timeout) == 1

    def test_noop_when_already_visible(self, qapp):
        widget = QWidget()
        surface = WindowsDesktopSurface()
        surface.install(widget)
        widget.show()
        surface._start_restore_monitor()
        assert surface._restore_timer is None

    def test_noop_when_timer_already_running(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface._start_restore_monitor()
        t1 = surface._restore_timer
        surface._start_restore_monitor()
        assert surface._restore_timer is t1


class TestStopRestoreMonitor:
    def test_stops_and_deletes_timer(self, qapp):
        widget = MagicMock()
        surface = _make_surface(widget)
        surface._start_restore_monitor()
        surface._stop_restore_monitor()
        assert surface._restore_timer is None

    def test_noop_when_no_timer(self, qapp):
        WindowsDesktopSurface()._stop_restore_monitor()


# ── _check_foreground ─────────────────────────────────────────────────────────

class TestCheckForeground:
    def test_desktop_class_triggers_reactivate(self, qapp):
        surface = _make_surface(visible=False)
        cb = MagicMock()
        surface._on_reactivate = cb
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="Progman")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()
        cb.assert_called_once()

    def test_workerw_triggers_reactivate(self, qapp):
        surface = _make_surface(visible=False)
        cb = MagicMock()
        surface._on_reactivate = cb
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="WorkerW")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()
        cb.assert_called_once()

    def test_tray_class_triggers_reactivate(self, qapp):
        surface = _make_surface(visible=False)
        cb = MagicMock()
        surface._on_reactivate = cb
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="Shell_TrayWnd")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()
        cb.assert_called_once()

    def test_empty_class_when_no_hwnd_triggers_reactivate(self, qapp):
        """No foreground window (hwnd=0) → win_class="" → in _DESKTOP_WIN_CLASSES."""
        surface = _make_surface(visible=False)
        cb = MagicMock()
        surface._on_reactivate = cb
        surface._restore_timer = MagicMock()
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll:
            windll.user32.GetForegroundWindow.return_value = 0
            surface._check_foreground()
        cb.assert_called_once()

    def test_other_class_does_not_trigger(self, qapp):
        surface = _make_surface(visible=False)
        cb = MagicMock()
        surface._on_reactivate = cb
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="NotDesktopClass")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()
        cb.assert_not_called()

    def test_stops_monitor_on_desktop_class(self, qapp):
        surface = _make_surface(visible=False)
        surface._on_reactivate = MagicMock()
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="Progman")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()
        surface._restore_timer.stop.assert_called_once()

    def test_stops_monitor_when_already_visible(self, qapp):
        surface = _make_surface(visible=True)
        surface._on_reactivate = MagicMock()
        surface._restore_timer = MagicMock()
        surface._check_foreground()
        surface._restore_timer.stop.assert_called_once()
        surface._on_reactivate.assert_not_called()

    def test_noop_when_no_callback(self, qapp):
        """Desktop class but no _on_reactivate set — must not raise."""
        surface = _make_surface(visible=False)
        surface._restore_timer = MagicMock()
        buf = MagicMock(value="Progman")
        with patch("infrastructure.windows.qt.desktop_surface.ctypes.windll") as windll, \
             patch("infrastructure.windows.qt.desktop_surface.ctypes.create_unicode_buffer",
                   return_value=buf):
            windll.user32.GetForegroundWindow.return_value = 0x100
            surface._check_foreground()


# ── _DESKTOP_WIN_CLASSES ──────────────────────────────────────────────────────

class TestDesktopWinClasses:
    def test_contains_all_known_classes(self):
        assert _DESKTOP_WIN_CLASSES == {"Progman", "WorkerW", "Shell_TrayWnd", ""}


# ── TimedLaunchHide ───────────────────────────────────────────────────────────

class TestTimedLaunchHide:
    def test_is_armed_false_initially(self, qapp):
        assert TimedLaunchHide(on_hide=MagicMock()).is_armed is False

    def test_arm_sets_is_armed(self, qapp):
        tlh = TimedLaunchHide(on_hide=MagicMock())
        tlh.arm(0)
        assert tlh.is_armed is True

    def test_cancel_clears_is_armed(self, qapp):
        tlh = TimedLaunchHide(on_hide=MagicMock())
        tlh.arm(0)
        tlh.cancel()
        assert tlh.is_armed is False

    def test_cancel_noop_when_not_armed(self, qapp):
        TimedLaunchHide(on_hide=MagicMock()).cancel()

    def test_arm_after_arm_replaces_timer(self, qapp):
        tlh = TimedLaunchHide(on_hide=MagicMock(), delay_ms=100)
        tlh.arm(0)
        t1 = tlh._timer
        tlh.arm(0)
        assert tlh._timer is not t1
        assert tlh.is_armed is True

    def test_fire_calls_on_hide_and_clears_armed(self, qapp):
        on_hide = MagicMock()
        tlh = TimedLaunchHide(on_hide=on_hide)
        tlh.arm(0)
        tlh._fire()
        on_hide.assert_called_once()
        assert tlh.is_armed is False

    def test_fire_cancels_timer(self, qapp):
        on_hide = MagicMock()
        tlh = TimedLaunchHide(on_hide=on_hide)
        tlh.arm(0)
        tlh._fire()
        assert tlh._timer is None

    def test_arm_stores_arbitrary_idx(self, qapp):
        on_hide = MagicMock()
        tlh = TimedLaunchHide(on_hide=on_hide)
        tlh.arm(42)
        tlh._fire()
        on_hide.assert_called_once()


