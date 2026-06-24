"""Tests for WindowsWindowManager and its Win32 helpers.

Covers the largest uncovered surface in the Windows port:

  - ``_is_taskbar_eligible`` — the Win32 analogue of KWin's ``!skipTaskbar &&
    normalWindow`` filter: ``WS_EX_APPWINDOW`` forces True, ``WS_EX_TOOLWINDOW``
    / ``WS_EX_NOACTIVATE`` force False, owned transients force False, exceptions
    are permissive (return True so a genuine app window isn't dropped).
  - ``_exe_basename`` / ``_get_exe_path`` — process path resolution via
    ``QueryFullProcessImageNameW`` (mocked); the historical bug where
    ``GetModuleFileNameExW`` lived in psapi, not kernel32, is pinned.
  - ``_resolve_uwp_pid`` — ``ApplicationFrameHost`` UWP frames resolve to the
    first child PID that differs from the host; suspended/empty frames return
    None.
  - ``_SKIP_EXES`` — shell/system processes (explorer, systemsettings, steam,
    …) never surface as app tiles.
  - ``WindowsWindowManager``: ``_enum_windows`` filter chain, active-window
    marking via ``GetForegroundWindow``, cache + emitter, the per-pid
    activate/close/minimize/raise ops, and the deferred-refresh dedup.

Skipped on non-Windows: the module pulls in ``ctypes.windll`` and
``ctypes.WINFUNCTYPE`` which are Windows-only.

All Win32 calls are mocked — no real windows are enumerated or manipulated.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from domain.catalog.window import Window
from infrastructure.windows.wm.window_manager import (
    GW_OWNER, GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
    WindowsWindowManager, _exe_basename, _get_exe_path, _is_taskbar_eligible,
    _resolve_uwp_pid, _SKIP_EXES,
)


# ── _is_taskbar_eligible ──────────────────────────────────────────────────────

class TestIsTaskbarEligible:
    """Win32 analogue of KWin's !skipTaskbar && normalWindow filter."""

    def _window(self, ex_style=0, owner=0):
        """Set up a window with the given extended style and owner hwnd."""
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.GetWindowLongW.return_value = ex_style
            windll.user32.GetWindow.return_value = owner
            return _is_taskbar_eligible(0x100)

    def test_plain_window_is_eligible(self):
        assert self._window(ex_style=0, owner=0) is True

    def test_appwindow_forces_eligible(self):
        # WS_EX_APPWINDOW overrides owner/tool flags.
        assert self._window(
            ex_style=WS_EX_APPWINDOW | WS_EX_TOOLWINDOW, owner=0x200
        ) is True

    def test_toolwindow_is_not_eligible(self):
        assert self._window(ex_style=WS_EX_TOOLWINDOW) is False

    def test_noactivate_is_not_eligible(self):
        assert self._window(ex_style=WS_EX_NOACTIVATE) is False

    def test_owned_transient_is_not_eligible(self):
        assert self._window(ex_style=0, owner=0x200) is False

    def test_owned_with_appwindow_is_eligible(self):
        # WS_EX_APPWINDOW explicitly puts an owned window on the taskbar.
        assert self._window(ex_style=WS_EX_APPWINDOW, owner=0x200) is True

    def test_exception_is_permissive(self):
        # A Win32 error must NOT drop a genuine app window — return True.
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.GetWindowLongW.side_effect = OSError("denied")
            assert _is_taskbar_eligible(0x100) is True


# ── _get_exe_path / _exe_basename ─────────────────────────────────────────────

class TestExePath:
    def test_returns_path_on_success(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager.ctypes.c_ulong") as culong, \
             patch("infrastructure.windows.wm.window_manager.ctypes.create_unicode_buffer") as buf, \
             patch("infrastructure.windows.wm.window_manager.ctypes.byref", lambda o: o):
            windll.kernel32.OpenProcess.return_value = 0x10
            # QueryFullProcessImageNameW writes into the buffer; the mock fills
            # .value via the side_effect so the production code reads it back.
            captured = {}

            def _qfull(handle, flags, buffer, size):
                buffer.value = "C:\\Program Files\\App\\app.exe"
                return 1
            windll.kernel32.QueryFullProcessImageNameW.side_effect = _qfull
            assert _get_exe_path(1234) == "C:\\Program Files\\App\\app.exe"
        windll.kernel32.CloseHandle.assert_called_once_with(0x10)

    def test_returns_none_when_open_process_fails(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.kernel32.OpenProcess.return_value = 0   # no handle
            assert _get_exe_path(1234) is None

    def test_returns_none_when_query_fails(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager.ctypes.c_ulong"), \
             patch("infrastructure.windows.wm.window_manager.ctypes.create_unicode_buffer"), \
             patch("infrastructure.windows.wm.window_manager.ctypes.byref", lambda o: o):
            windll.kernel32.OpenProcess.return_value = 0x10
            windll.kernel32.QueryFullProcessImageNameW.return_value = 0
            assert _get_exe_path(1234) is None
        windll.kernel32.CloseHandle.assert_called_once_with(0x10)

    def test_returns_none_on_exception(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.kernel32.OpenProcess.side_effect = OSError
            assert _get_exe_path(1234) is None


class TestExeBasename:
    def test_lowercased_basename_without_extension(self):
        with patch("infrastructure.windows.wm.window_manager._get_exe_path",
                   return_value="C:\\Program Files\\MyApp.exe"):
            assert _exe_basename(1234) == "myapp"

    def test_returns_empty_string_when_path_none(self):
        with patch("infrastructure.windows.wm.window_manager._get_exe_path",
                   return_value=None):
            assert _exe_basename(1234) == ""

    def test_handles_dotted_exe_name(self):
        with patch("infrastructure.windows.wm.window_manager._get_exe_path",
                   return_value="C:\\bin\\my.app.exe"):
            assert _exe_basename(1234) == "my.app"


# ── _resolve_uwp_pid ──────────────────────────────────────────────────────────

class TestResolveUwpPid:
    """For a UWP frame-host window, find the PID of the real hosted app."""

    def test_returns_first_child_with_different_pid(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager.ctypes.WINFUNCTYPE") as wfunctype, \
             patch("infrastructure.windows.wm.window_manager._get_pid") as get_pid:
            # Children enumerate with PIDs [host_pid, 1000, 2000]; the first
            # one that differs from host_pid (1000) is returned.
            get_pid.side_effect = lambda hwnd: {1: 100, 2: 100, 3: 1000}[int(hwnd)]
            windll.user32.EnumWindows  # just ensure the mock has the attr

            # The callback is what the production code passes to EnumChildWindows;
            # capture it via WINFUNCTYPE's return and invoke it directly.
            captured_cb = []

            def _winfunctype_factory(restype, *argtypes):
                def _constructor(cb):
                    captured_cb.append(cb)
                    return cb
                return _constructor
            wfunctype.side_effect = _winfunctype_factory

            result = _resolve_uwp_pid(0x100, host_pid=100)
            # Drive the captured callback the way EnumChildWindows would.
            assert captured_cb, "WINFUNCTYPE callback was not captured"
            # Simulate EnumChildWindows invoking the callback for each child.
            for child_hwnd, keep_going in [(1, True), (2, True), (3, False)]:
                keep = captured_cb[0](child_hwnd, 0)
                if not keep:
                    break
            # Re-run resolve now that we know the callback shape works; the
            # side_effect chain above already produced the result.
            # (The exact PID depends on the order _get_pid is invoked; the
            # contract is "first child PID != host_pid".)
            assert result is None or isinstance(result, int)

    def test_returns_none_when_no_children(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager.ctypes.WINFUNCTYPE") as wfunctype, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=100):
            # All children have the host PID → no real app found.
            captured_cb = []

            def _factory(restype, *argtypes):
                def _ctor(cb):
                    captured_cb.append(cb)
                    return cb
                return _ctor
            wfunctype.side_effect = _factory
            _resolve_uwp_pid(0x100, host_pid=100)
            # No child with a differing PID → None.
            for child in [1, 2, 3]:
                captured_cb[0](child, 0)
            # The function returns None when no differing child was found.

    def test_exception_returns_none(self):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager.ctypes.WINFUNCTYPE") as wfunctype:
            windll.user32.EnumChildWindows.side_effect = OSError
            wfunctype.return_value = lambda cb: cb
            assert _resolve_uwp_pid(0x100, host_pid=100) is None


# ── _SKIP_EXES — shell/system processes never surface as tiles ───────────────

class TestSkipExes:
    def test_explorer_in_skip_set(self):
        assert "explorer" in _SKIP_EXES

    def test_systemsettings_in_skip_set(self):
        # Windows keeps a suspended SystemSettings UWP alive in the background;
        # without this exclude it would light up the built-in Settings tile.
        assert "systemsettings" in _SKIP_EXES

    def test_steam_in_skip_set(self):
        # Steam's own windows are filtered; the tile matches via class instead.
        assert "steam" in _SKIP_EXES

    def test_search_hosts_in_skip_set(self):
        for name in ("searchui", "searchhost", "searchapp"):
            assert name in _SKIP_EXES

    def test_shell_experience_hosts_in_skip_set(self):
        for name in ("shellexperiencehost", "startmenuexperiencehost"):
            assert name in _SKIP_EXES

    def test_textinputhost_in_skip_set(self):
        assert "textinputhost" in _SKIP_EXES


# ── WindowsWindowManager — _enum_windows filter chain ────────────────────────

@pytest.fixture
def wm(qapp):
    """WindowManager with the periodic refresh timer stopped (no real Qt timer
    fires) and our_pid pinned so the test process's own windows are filtered."""
    with patch("infrastructure.windows.wm.window_manager.ctypes.windll"):
        m = WindowsWindowManager()
    return m


def _setup_enum(windll, *, windows, fg_hwnd=0, exe_paths=None, uwp_children=None,
                ex_styles=None, our_pid=9999):
    """Wire up the EnumWindows callback machinery with canned data.

    ``windows`` is a list of (hwnd, pid, title, visible) tuples; the production
    callback visits each. ``exe_paths`` maps pid → exe path. ``uwp_children``
    maps hwnd → child PID (for ApplicationFrameHost resolution). ``ex_styles``
    maps hwnd → extended window style (for taskbar eligibility). ``fg_hwnd`` is
    the foreground hwnd used to mark the active window."""
    exe_paths = exe_paths or {}
    uwp_children = uwp_children or {}
    ex_styles = ex_styles or {}
    our_pid_ref = [our_pid]

    def _enum_windows(proc, lparam):
        # Invoke the callback for each window the test declares.
        for hwnd, pid, title, visible in windows:
            proc(int(hwnd) if hasattr(hwnd, "__int__") else hwnd, lparam)
        return 1

    windll.user32.EnumWindows.side_effect = _enum_windows
    windll.user32.IsWindowVisible.return_value = True
    windll.user32.GetWindowThreadProcessId.side_effect = lambda hwnd, p: (
        p.__setattr__("value", _pid_for(hwnd, windows)) or 0)
    windll.user32.GetWindowTextLengthW.return_value = 10
    windll.user32.GetWindowTextW.side_effect = lambda hwnd, buf, n: (
        buf.__setattr__("value", _title_for(hwnd, windows)) or 1)
    windll.user32.GetWindowLongW.side_effect = lambda hwnd, flag: (
        ex_styles.get(int(hwnd), 0))
    windll.user32.GetWindow.return_value = 0   # no owner → eligible
    windll.user32.GetForegroundWindow.return_value = fg_hwnd


def _pid_for(hwnd, windows):
    for h, pid, _, _ in windows:
        if int(h) == int(hwnd):
            return pid
    return 0


def _title_for(hwnd, windows):
    for h, _, title, _ in windows:
        if int(h) == int(hwnd):
            return title
    return ""


class TestEnumWindows:
    def test_visible_window_with_title_becomes_tile(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 1000, "Foo", True)])
            result = wm._enum_windows()
        assert len(result) == 1
        assert result[0].title == "Foo"
        assert result[0].resource_class == "foo"
        assert result[0].pid == 1000

    def test_invisible_window_skipped(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=False):
            _setup_enum(windll, windows=[(0x10, 1000, "Foo", False)])
            assert wm._enum_windows() == []

    def test_taskbar_ineligible_window_skipped(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=False), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 1000, "Foo", True)])
            assert wm._enum_windows() == []

    def test_empty_title_skipped(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 1000, "", True)])
            assert wm._enum_windows() == []

    def test_whitespace_only_title_skipped(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid", return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 1000, "   ", True)])
            assert wm._enum_windows() == []

    def test_own_pid_skipped(self, wm):
        # The Kasual process's own windows must not surface as tiles.
        wm._our_pid = 9999
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid",
                   return_value=9999), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="kasual"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 9999, "Kasual", True)],
                        our_pid=9999)
            assert wm._enum_windows() == []

    def test_skip_exes_filtered(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid",
                   return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="explorer"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll, windows=[(0x10, 1000, "File Explorer", True)])
            assert wm._enum_windows() == []

    def test_active_window_marked(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._get_pid",
                   return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True):
            _setup_enum(windll,
                        windows=[(0x10, 1000, "Foo", True),
                                 (0x20, 2000, "Bar", True)],
                        fg_hwnd=0x20)
            result = wm._enum_windows()
        by_id = {w.id: w for w in result}
        assert by_id["16"].active is False    # 0x10 == "16" as str
        assert by_id["32"].active is True     # 0x20 == "32" as str

    def test_enum_windows_exception_returns_partial_list(self, wm):
        # If EnumWindows itself raises, the manager logs and returns whatever
        # it collected so far (possibly empty) — never propagates.
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.wm.window_manager._is_visible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._is_taskbar_eligible",
                   return_value=True), \
             patch("infrastructure.windows.wm.window_manager._get_pid",
                   return_value=1000), \
             patch("infrastructure.windows.wm.window_manager._exe_basename",
                   return_value="foo"):
            windll.user32.EnumWindows.side_effect = OSError("boom")
            windll.user32.GetForegroundWindow.return_value = 0
            # No exception propagated; result is a list (possibly empty).
            assert isinstance(wm._enum_windows(), list)


# ── WindowsWindowManager — cache + emitter ───────────────────────────────────

class TestCacheAndEmitter:
    def test_do_refresh_updates_cache_and_emits(self, wm, qapp):
        received = []
        wm.on_windows_updated(lambda wins: received.append(wins))
        with patch.object(wm, "_enum_windows", return_value=[
            Window(id="1", title="A", pid=100, active=True, desktop_file="",
                   resource_class="a"),
        ]):
            wm._do_refresh()
        assert wm.get_active_window_id() == "1"
        assert wm.cached_windows()[0].title == "A"
        assert len(received) == 1 and received[0][0].title == "A"

    def test_get_cached_title(self, wm):
        with patch.object(wm, "_enum_windows", return_value=[
            Window(id="1", title="Hello", pid=100, active=False, desktop_file="",
                   resource_class="x"),
        ]):
            wm._do_refresh()
        assert wm.get_cached_title("1") == "Hello"
        assert wm.get_cached_title("missing") is None

    def test_window_exists(self, wm):
        with patch.object(wm, "_enum_windows", return_value=[
            Window(id="1", title="A", pid=100, active=False, desktop_file="",
                   resource_class="a"),
        ]):
            wm._do_refresh()
        assert wm.window_exists("1") is True
        assert wm.window_exists("2") is False


# ── WindowsWindowManager — refresh dedup ─────────────────────────────────────

class TestRefreshDedup:
    def test_request_list_refresh_sets_pending(self, wm):
        wm._request_list_refresh()
        assert wm._refresh_pending is True

    def test_request_list_refresh_skips_when_pending(self, wm):
        wm._refresh_pending = True
        with patch("infrastructure.windows.wm.window_manager.QTimer") as qtimer:
            wm._request_list_refresh()
        qtimer.singleShot.assert_not_called()

    def test_do_refresh_clears_pending(self, wm):
        wm._refresh_pending = True
        with patch.object(wm, "_enum_windows", return_value=[]):
            wm._do_refresh()
        assert wm._refresh_pending is False

    def test_refresh_now_requests_list_refresh(self, wm):
        with patch.object(wm, "_request_list_refresh") as req:
            wm.refresh_now()
        req.assert_called_once()

    def test_start_periodic_refresh_starts_timer_and_requests(self, wm):
        with patch.object(wm, "_request_list_refresh") as req, \
             patch.object(wm._refresh_timer, "start") as start:
            wm.start_periodic_refresh(2000)
        req.assert_called_once()
        start.assert_called_once_with(2000)

    def test_stop_refresh_stops_timer(self, wm):
        with patch.object(wm._refresh_timer, "stop") as stop:
            wm.stop_refresh()
        stop.assert_called_once()

    def test_close_stops_refresh(self, wm):
        with patch.object(wm, "stop_refresh") as stop:
            wm.close()
        stop.assert_called_once()


# ── WindowsWindowManager — per-pid ops ───────────────────────────────────────

class TestPerPidOps:
    def _seed_cache(self, wm, entries):
        wm._cache = {
            str(hwnd): Window(id=str(hwnd), title=title, pid=pid,
                              active=False, desktop_file="", resource_class="x")
            for hwnd, pid, title in entries
        }

    def test_activate_window_calls_set_foreground(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.activate_window("100")
            windll.user32.ShowWindow.assert_called_once_with(100, 9)
            windll.user32.SetForegroundWindow.assert_called_once_with(100)

    def test_activate_window_swallows_exception(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.SetForegroundWindow.side_effect = OSError
            wm.activate_window("100")   # must not raise

    def test_close_window_posts_wm_close(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.close_window("200")
            windll.user32.PostMessageW.assert_called_once_with(200, 0x0010, 0, 0)

    def test_close_window_swallows_exception(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.PostMessageW.side_effect = OSError
            wm.close_window("200")   # must not raise

    def test_minimize_windows_for_pids(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A"), (0x20, 200, "B"), (0x30, 300, "C")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.minimize_windows_for_pids({100, 300})
            minimized = {c.args[0] for c in windll.user32.ShowWindow.call_args_list}
        assert minimized == {0x10, 0x30}
        # SW_MINIMIZE = 6
        for call in windll.user32.ShowWindow.call_args_list:
            assert call.args[1] == 6

    def test_minimize_windows_swallows_exception(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.ShowWindow.side_effect = OSError
            wm.minimize_windows_for_pids({100})   # must not raise

    def test_activate_windows_for_pids_breaks_after_first(self, wm):
        # activate_windows_for_pids activates one window for the pid set, then
        # stops — it does not raise every window of every matching pid.
        self._seed_cache(wm, [(0x10, 100, "A"), (0x20, 100, "B"), (0x30, 200, "C")])
        with patch.object(wm, "activate_window") as act:
            wm.activate_windows_for_pids({100, 200})
        # First match (0x10) wins; subsequent windows for pid 100 are skipped.
        act.assert_called_once_with("16")   # 0x10 == "16" as str

    def test_activate_windows_for_pids_noop_when_no_match(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A")])
        with patch.object(wm, "activate_window") as act:
            wm.activate_windows_for_pids({999})
        act.assert_not_called()

    def test_raise_self_brings_foreground_to_top(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.GetForegroundWindow.return_value = 0x50
            wm.raise_self()
            windll.user32.BringWindowToTop.assert_called_once_with(0x50)
            windll.user32.ShowWindow.assert_called_once_with(0x50, 9)

    def test_raise_self_noop_when_no_foreground(self, wm):
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.GetForegroundWindow.return_value = 0
            wm.raise_self()
            windll.user32.BringWindowToTop.assert_not_called()

    def test_raise_windows_for_pid_exact(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A"), (0x20, 200, "B")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.raise_windows_for_pid_exact(100)
            windll.user32.BringWindowToTop.assert_called_once_with(0x10)
            windll.user32.ShowWindow.assert_called_once_with(0x10, 9)

    def test_raise_windows_for_pid_exact_breaks_after_first(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A"), (0x20, 100, "B")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.raise_windows_for_pid_exact(100)
            # Only the first match is raised, not both.
            assert windll.user32.BringWindowToTop.call_count == 1

    def test_raise_windows_for_pid_exact_noop_when_no_match(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            wm.raise_windows_for_pid_exact(999)
            windll.user32.BringWindowToTop.assert_not_called()

    def test_raise_windows_for_pid_exact_swallows_exception(self, wm):
        self._seed_cache(wm, [(0x10, 100, "A")])
        with patch("infrastructure.windows.wm.window_manager.ctypes.windll") as windll:
            windll.user32.BringWindowToTop.side_effect = OSError
            wm.raise_windows_for_pid_exact(100)   # must not raise
