"""Windows window manager using Win32 EnumWindows API."""

import ctypes
import logging
import os
from collections.abc import Callable
from typing import _ProtocolMeta

from PyQt6.QtCore import QObject, QTimer

from domain.catalog.window import Window
from domain.lifecycle.window_manager import WindowManager
from domain.shared.event_emitter import EventEmitter, Unsubscribe

logger = logging.getLogger(__name__)


class _Meta(type(QObject), _ProtocolMeta):
    """Combined metaclass so a QObject can declare it implements a Protocol port."""


def _get_pid(hwnd: int) -> int:
    """Get process ID for a window handle."""
    try:
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0


def _get_window_text(hwnd: int) -> str:
    """Get window title text."""
    try:
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
    except Exception:
        pass
    return ""


def _is_visible(hwnd: int) -> bool:
    """Check if window is visible."""
    try:
        user32 = ctypes.windll.user32
        return bool(user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def _get_exe_path(pid: int) -> str | None:
    """Get executable path for a process ID."""
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            try:
                buffer = ctypes.create_unicode_buffer(260)
                size = ctypes.windll.kernel32.GetModuleFileNameExW(handle, 0, buffer, 260)
                if size > 0:
                    return buffer.value
            finally:
                kernel32.CloseHandle(handle)
    except Exception:
        pass
    return None


class WindowsWindowManager(QObject, WindowManager, metaclass=_Meta):
    """Manages windows using Win32 EnumWindows API."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._windows_emitter = EventEmitter[list[Window]]()
        self._cache: dict[str, Window] = {}
        self._active_window_id: str | None = None
        self._our_pid = os.getpid()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._refresh_pending = False

    def start_periodic_refresh(self, interval_ms: int = 3000) -> None:
        self._request_list_refresh()
        self._refresh_timer.start(interval_ms)

    def stop_refresh(self) -> None:
        self._refresh_timer.stop()

    def refresh_now(self) -> None:
        self._request_list_refresh()

    def _request_list_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        windows = self._enum_windows()
        self._cache = {w.id: w for w in windows}
        self._active_window_id = next(
            (w.id for w in windows if w.active), None
        )
        self._windows_emitter.emit(windows)
        logger.debug("Windows list: %d, active: %s", len(self._cache), self._active_window_id)

    def _enum_windows(self) -> list[Window]:
        """Enumerate all visible windows using Win32 API."""
        windows = []
        our_pid = self._our_pid

        try:
            user32 = ctypes.windll.user32

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def enum_proc(hwnd, lparam):
                try:
                    if not _is_visible(int(hwnd)):
                        return True

                    pid = _get_pid(int(hwnd))
                    if pid == 0 or pid == our_pid:
                        return True

                    title = _get_window_text(int(hwnd))
                    if not title or len(title.strip()) == 0:
                        return True

                    exe = _get_exe_path(pid) or ""
                    desktop_file = ""
                    resource_class = ""

                    if exe:
                        basename = os.path.splitext(os.path.basename(exe))[0].lower()
                        if basename not in ("explorer", "steam", "steamwebhelper",
                                           "applicationframehost", "searchui", "searchhost"):
                            windows.append(Window(
                                id=str(int(hwnd)),
                                title=title,
                                pid=pid,
                                active=False,
                                desktop_file=desktop_file,
                                resource_class=resource_class,
                            ))
                except Exception as e:
                    logger.debug("Error enumerating window 0x%x: %s", hwnd, e)
                return True

            user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
        except Exception as e:
            logger.error("EnumWindows failed: %s", e)

        active_hwnd = user32.GetForegroundWindow()
        if active_hwnd:
            active_id = str(active_hwnd)
            result = []
            for w in windows:
                if w.id == active_id:
                    result.append(Window(
                        id=w.id,
                        title=w.title,
                        pid=w.pid,
                        active=True,
                        desktop_file=w.desktop_file,
                        resource_class=w.resource_class,
                    ))
                else:
                    result.append(w)
            windows = result

        return windows

    def get_active_window_id(self) -> str | None:
        return self._active_window_id

    def get_cached_title(self, window_id: str) -> str | None:
        w = self._cache.get(window_id)
        return w.title if w else None

    def activate_window(self, window_id: str) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = int(window_id)
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            logger.info("Activated window: %s", window_id)
        except Exception as e:
            logger.warning("Failed to activate window %s: %s", window_id, e)

    def close_window(self, window_id: str) -> None:
        try:
            user32 = ctypes.windll.user32
            WM_CLOSE = 0x0010
            hwnd = int(window_id)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            logger.info("Closed window: %s", window_id)
        except Exception as e:
            logger.warning("Failed to close window %s: %s", window_id, e)

    def minimize_windows_for_pids(self, pids: set[int]) -> None:
        try:
            user32 = ctypes.windll.user32
            for window_id, window in self._cache.items():
                if window.pid in pids:
                    hwnd = int(window_id)
                    user32.ShowWindow(hwnd, 6)
            logger.info("Minimized windows for pids: %s", pids)
        except Exception as e:
            logger.warning("Failed to minimize windows: %s", e)

    def activate_windows_for_pids(self, pids: set[int]) -> None:
        for window_id, window in self._cache.items():
            if window.pid in pids:
                self.activate_window(window_id)
                break

    def raise_self(self) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.BringWindowToTop(hwnd)
                user32.ShowWindow(hwnd, 9)
        except Exception as e:
            logger.warning("Failed to raise self: %s", e)

    def raise_windows_for_pid_exact(self, pid: int) -> None:
        try:
            user32 = ctypes.windll.user32
            for window_id, window in self._cache.items():
                if window.pid == pid:
                    hwnd = int(window_id)
                    user32.BringWindowToTop(hwnd)
                    user32.ShowWindow(hwnd, 9)
                    break
        except Exception as e:
            logger.warning("Failed to raise windows for pid %d: %s", pid, e)

    def window_exists(self, window_id: str) -> bool:
        return window_id in self._cache

    def cached_windows(self) -> list[Window]:
        return list(self._cache.values())

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Unsubscribe:
        return self._windows_emitter.subscribe(handler)

    def close(self) -> None:
        self.stop_refresh()