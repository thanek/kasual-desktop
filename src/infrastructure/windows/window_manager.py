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


# Win32 extended-window-style flags and GetWindow relation constants used by
# _is_taskbar_eligible — the analogue of KWin's `!skipTaskbar && normalWindow`
# filter (see infrastructure/system/window_manager.py::_LIST_SCRIPT).
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW  = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE      = -20
GW_OWNER         = 4


def _is_taskbar_eligible(hwnd: int) -> bool:
    """Whether *hwnd* would appear on the Windows taskbar.

    Suspended UWP frames (e.g. a background ``SystemSettings``
    ``ApplicationFrameWindow``), tool windows, and owned transients (dialogs)
    are not taskbar-eligible and must not be treated as live app tiles —
    otherwise a built-in tile whose ``wm_class`` matches a background UWP
    lights up as "running" and can't be closed (the UWP is suspended, so
    ``WM_CLOSE`` is never pumped).
    """
    try:
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        # WS_EX_APPWINDOW forces taskbar eligibility (overrides owner/tool flags).
        if ex_style & WS_EX_APPWINDOW:
            return True
        if ex_style & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
            return False
        # An owned top-level window (transient/dialog) is not on the taskbar
        # unless WS_EX_APPWINDOW is set (handled above).
        if user32.GetWindow(hwnd, GW_OWNER):
            return False
        return True
    except Exception:
        # Be permissive on error — don't drop genuine app windows.
        return True


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _get_exe_path(pid: int) -> str | None:
    """Full executable path for a process ID, or None.

    Uses QueryFullProcessImageNameW (kernel32) — the modern, reliable call.
    The older GetModuleFileNameExW lives in psapi, not kernel32, so the previous
    kernel32.GetModuleFileNameExW raised AttributeError and silently returned None
    for *every* window, leaving the whole window list empty.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            try:
                size = ctypes.c_ulong(260)
                buffer = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    return buffer.value
            finally:
                kernel32.CloseHandle(handle)
    except Exception:
        pass
    return None


def _exe_basename(pid: int) -> str:
    """Lowercased executable basename (no extension) for *pid*, e.g. 'systemsettings'."""
    exe = _get_exe_path(pid) or ""
    return os.path.splitext(os.path.basename(exe))[0].lower() if exe else ""


def _resolve_uwp_pid(hwnd: int, host_pid: int) -> int | None:
    """For a UWP frame-host window, find the PID of the real hosted app.

    A UWP app's top-level ``ApplicationFrameWindow`` belongs to
    ApplicationFrameHost.exe; the actual app (e.g. SystemSettings.exe) owns a
    child ``Windows.UI.Core.CoreWindow``. Return the first child PID that differs
    from the host, or None."""
    found = [None]

    EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(child, _lparam):
        cpid = _get_pid(int(child))
        if cpid and cpid != host_pid:
            found[0] = cpid
            return False
        return True

    try:
        ctypes.windll.user32.EnumChildWindows(int(hwnd), EnumChildProc(_cb), 0)
    except Exception:
        pass
    return found[0]


# Shell/system processes whose windows are never app tiles.
# ``systemsettings`` is included because Windows keeps a suspended
# ``SystemSettings.exe`` UWP alive in the background — visible to
# ``EnumWindows`` but not on the taskbar—so without this exclude it would
# surface as a spurious dynamic tile (and light up the built-in Settings
# tile as "running"). The built-in Settings tile launches Settings via
# ``ms-settings:`` directly; it doesn't need the window enumerator.
_SKIP_EXES = frozenset({
    "explorer", "searchui", "searchhost", "searchapp", "shellexperiencehost",
    "startmenuexperiencehost", "textinputhost", "steam", "steamwebhelper",
    "systemsettings",
})


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

                    # Win32 analogue of KWin's `!skipTaskbar && normalWindow`:
                    # drop suspended UWP frames, tool windows and owned
                    # transients so they don't surface as running tiles.
                    if not _is_taskbar_eligible(int(hwnd)):
                        return True

                    pid = _get_pid(int(hwnd))
                    if pid == 0 or pid == our_pid:
                        return True

                    title = _get_window_text(int(hwnd))
                    if not title or len(title.strip()) == 0:
                        return True

                    basename = _exe_basename(pid)
                    win_pid = pid
                    if basename == "applicationframehost":
                        # UWP window: the frame host isn't the app. Resolve the
                        # real hosted process (e.g. SystemSettings) so the tile
                        # can be matched by its StartupWMClass / resourceClass.
                        real_pid = _resolve_uwp_pid(int(hwnd), pid)
                        if real_pid is None:
                            return True
                        win_pid = real_pid
                        basename = _exe_basename(real_pid)
                        # If resolve returned another ApplicationFrameHost
                        # (an edge case for suspended/empty UWP frames), there
                        # is no real hosted app to tile — skip.
                        if basename == "applicationframehost":
                            return True

                    if basename and basename not in _SKIP_EXES:
                        # resource_class carries the exe basename — the Windows
                        # analogue of an X11/Wayland app id — so Window.matches_app
                        # can attribute the window to a tile (command basename or
                        # StartupWMClass).
                        windows.append(Window(
                            id=str(int(hwnd)),
                            title=title,
                            pid=win_pid,
                            active=False,
                            desktop_file="",
                            resource_class=basename,
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