"""Unit tests for WindowsAppManager (Windows ShellExecuteEx/subprocess version).

Mirror of the Linux ``test_app_manager.py``: same lifecycle bookkeeping (initial
state, is_running/running_idxs/running_pid/all_running_pids, _on_finished,
terminate/force-kill, swap_indices, remove_index) plus the Windows-specific
launch paths:

  - ``.lnk`` and ``ms-*`` protocol schemes go through ``ShellExecuteEx``;
  - a normal ``.exe`` is spawned via ``subprocess.Popen`` with
    ``CREATE_NO_WINDOW`` and a ``STARTUPINFO`` that forces a shown window;
  - a command not on PATH falls back to ``os.startfile``;
  - the Win32 process HANDLE wrapper (``_WinHandle``) tracks pid, exit code,
    and termination via ``WaitForSingleObject``/``GetExitCodeProcess``.

Skipped on non-Windows: the module pulls in ``ctypes.windll``,
``subprocess.STARTUPINFO`` and ``os.startfile`` which are Windows-only.

subprocess.Popen, threading.Thread, ctypes.windll.shell32 and
ctypes.windll.kernel32 are always mocked — tests don't start any real
processes, threads or Win32 calls.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from infrastructure.windows.catalog.app_manager import (
    CREATE_NO_WINDOW,
    WAIT_TIMEOUT,
    WindowsAppManager,
    _WinHandle,
)


def _make_manager():
    return WindowsAppManager()


def _running_proc(pid=1234):
    """Mock procesu który jeszcze działa (poll() → None)."""
    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = pid
    return proc


def _exited_proc():
    """Mock procesu który już zakończył działanie (poll() → 0)."""
    proc = MagicMock()
    proc.poll.return_value = 0
    return proc


# ── Stan początkowy ────────────────────────────────────────────────────────────

class TestInitialState:
    def test_not_running(self, qapp):
        assert _make_manager().is_running() is False

    def test_is_running_specific_not_running(self, qapp):
        assert _make_manager().is_running(0) is False

    def test_running_idxs_empty(self, qapp):
        assert _make_manager().running_idxs() == []

    def test_all_running_pids_empty(self, qapp):
        assert _make_manager().all_running_pids() == []


# ── is_running / running_idxs / running_pid / all_running_pids ────────────────

class TestIsRunning:
    def test_true_for_specific_running_idx(self, qapp):
        am = _make_manager()
        am._processes[2] = _running_proc()
        assert am.is_running(2) is True

    def test_false_for_exited_process(self, qapp):
        am = _make_manager()
        am._processes[2] = _exited_proc()
        assert am.is_running(2) is False

    def test_false_for_unknown_idx(self, qapp):
        am = _make_manager()
        assert am.is_running(99) is False

    def test_no_arg_true_when_any_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        assert am.is_running() is True

    def test_no_arg_false_when_all_exited(self, qapp):
        am = _make_manager()
        am._processes[0] = _exited_proc()
        assert am.is_running() is False

    def test_running_idxs_returns_only_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=1)
        am._processes[1] = _exited_proc()
        am._processes[2] = _running_proc(pid=2)
        assert sorted(am.running_idxs()) == [0, 2]

    def test_running_pid_returns_pid(self, qapp):
        am = _make_manager()
        am._processes[3] = _running_proc(pid=4242)
        assert am.running_pid(3) == 4242

    def test_running_pid_none_when_not_running(self, qapp):
        am = _make_manager()
        assert am.running_pid(0) is None

    def test_running_pid_none_for_exited(self, qapp):
        am = _make_manager()
        am._processes[0] = _exited_proc()
        assert am.running_pid(0) is None

    def test_all_running_pids(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=100)
        am._processes[1] = _running_proc(pid=200)
        am._processes[2] = _exited_proc()
        assert sorted(am.all_running_pids()) == [100, 200]


# ── launch — zwykły .exe przez subprocess.Popen ────────────────────────────────

class TestLaunchExe:
    def _launch(self, am, idx=0, command="C:\\app\\foo.exe", args=None, pid=1234,
                exists=True):
        """Run a normal-exe launch with Popen + Thread mocked.

        ``exists`` controls ``os.path.exists`` for the command — the production
        code routes a missing file to ``_find_in_path`` and then ``os.startfile``
        fallback, so tests that want the Popen path must lie that the file exists.
        """
        proc = _running_proc(pid=pid)
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"), \
             patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=exists):
            am.launch(idx, command, args or [])
        return popen, proc

    def test_creates_process_with_command_and_args(self, qapp):
        import subprocess
        am = _make_manager()
        popen, _ = self._launch(am, command="C:\\app\\foo.exe", args=["--flag", "x"])
        args, kwargs = popen.call_args
        assert args[0] == ["C:\\app\\foo.exe", "--flag", "x"]
        assert kwargs["creationflags"] == CREATE_NO_WINDOW
        # STARTUPINFO forces a shown window (no console flash on launch).
        si = kwargs["startupinfo"]
        assert isinstance(si, subprocess.STARTUPINFO)
        assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert si.wShowWindow == 1

    def test_args_converted_to_strings(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="cmd.exe", args=[1, 2, 3])
        assert popen.call_args[0][0] == ["cmd.exe", "1", "2", "3"]

    def test_missing_args_key_defaults_to_empty(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="C:\\app\\cmd.exe")
        assert popen.call_args[0][0] == ["C:\\app\\cmd.exe"]

    def test_env_merges_app_env(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=1234)
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(0, "cmd.exe", [], {"FOO": "bar"})
        env = popen.call_args.kwargs["env"]
        assert env["FOO"] == "bar"

    def test_emits_app_started(self, qapp):
        am = _make_manager()
        received = []
        am.on_started(lambda e: received.append(e.idx))
        self._launch(am, idx=3)
        assert received == [3]

    def test_ignored_when_same_idx_already_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen") as popen:
            am.launch(0, "foo.exe")
        popen.assert_not_called()

    def test_allows_different_idxs_simultaneously(self, qapp):
        am = _make_manager()
        self._launch(am, idx=0, pid=100)
        self._launch(am, idx=1, pid=200)
        assert sorted(am.running_idxs()) == [0, 1]

    def test_starts_monitor_thread(self, qapp):
        am = _make_manager()
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", return_value=_running_proc()), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread") as mock_thread, \
             patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=True):
            am.launch(0, "foo.exe")
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_returns_true_on_successful_launch(self, qapp):
        am = _make_manager()
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", return_value=_running_proc()), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"), \
             patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=True):
            assert am.launch(0, "foo.exe") is True

    def test_returns_false_when_already_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen"):
            assert am.launch(0, "foo.exe") is False

    def test_returns_false_and_emits_failed_on_file_not_found(self, qapp):
        am = _make_manager()
        failed = []
        am.on_launch_failed(lambda e: failed.append((e.idx, e.error)))
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", side_effect=FileNotFoundError):
            assert am.launch(2, "C:\\nope.exe") is False
        assert failed and failed[0][0] == 2
        assert not am.is_running(2)

    def test_returns_false_on_permission_error(self, qapp):
        am = _make_manager()
        with patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", side_effect=PermissionError):
            assert am.launch(0, "C:\\secret.exe") is False


# ── launch — PATH resolution ──────────────────────────────────────────────────

class TestLaunchPathResolution:
    def test_find_in_path_returns_absolute_existing(self, qapp):
        am = _make_manager()
        with patch("infrastructure.windows.catalog.app_manager.os.path.isabs", return_value=True), \
             patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=True):
            assert am._find_in_path("C:\\bin\\app.exe") == "C:\\bin\\app.exe"

    def test_find_in_path_resolves_dir(self, qapp, tmp_path):
        exe = tmp_path / "tool.exe"
        exe.write_text("x")
        am = _make_manager()
        with patch.dict("os.environ", {"PATH": str(tmp_path)}):
            assert am._find_in_path("tool") == str(exe)

    def test_find_in_path_appends_exe_extension(self, qapp, tmp_path):
        exe = tmp_path / "thing.exe"
        exe.write_text("x")
        am = _make_manager()
        with patch.dict("os.environ", {"PATH": str(tmp_path)}):
            assert am._find_in_path("thing") == str(exe)

    def test_find_in_path_returns_none_when_missing(self, qapp):
        am = _make_manager()
        with patch.dict("os.environ", {"PATH": "C:\\empty"}):
            assert am._find_in_path("nope") is None

    def test_launch_uses_path_resolved_target(self, qapp, tmp_path):
        exe = tmp_path / "tool.exe"
        exe.write_text("x")
        am = _make_manager()
        proc = _running_proc(pid=555)
        with patch.dict("os.environ", {"PATH": str(tmp_path)}), \
             patch("infrastructure.windows.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(0, "tool")
        assert popen.call_args[0][0][0] == str(exe)


# ── launch — fallback os.startfile dla nieistniejącego pliku i braku w PATH ──

class TestLaunchStartfileFallback:
    def test_startfile_emits_app_started_and_returns_true(self, qapp):
        am = _make_manager()
        received = []
        am.on_started(lambda e: received.append(e.idx))
        with patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=False), \
             patch.object(WindowsAppManager, "_find_in_path", return_value=None), \
             patch("infrastructure.windows.catalog.app_manager.os.startfile") as startfile:
            assert am.launch(4, "weird-command") is True
        startfile.assert_called_once_with("weird-command")
        assert received == [4]

    def test_startfile_failure_returns_false_and_emits_failed(self, qapp):
        am = _make_manager()
        failed = []
        am.on_launch_failed(lambda e: failed.append(e.idx))
        with patch("infrastructure.windows.catalog.app_manager.os.path.exists", return_value=False), \
             patch.object(WindowsAppManager, "_find_in_path", return_value=None), \
             patch("infrastructure.windows.catalog.app_manager.os.startfile", side_effect=OSError("no")):
            assert am.launch(4, "weird-command") is False
        assert failed == [4]


# ── launch — .lnk / ms-* przez ShellExecuteEx ──────────────────────────────────

class TestLaunchShellExecute:
    def _shell_launch(self, am, idx=0, command="ms-settings:",
                      hProcess=0x100, pid=4321):
        """Run a shell-execute launch with mocked Win32 calls.

        Patches ``ctypes.byref`` to pass the struct directly so the
        ``ShellExecuteExW`` side_effect can mutate ``sei.hProcess`` — the real
        Win32 call writes the handle back through the byref pointer.
        Returns the windll mock and the SHELLEXECUTEINFO instance."""
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj), \
             patch("infrastructure.windows.catalog.app_manager.ctypes.sizeof", return_value=64), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            windll.shell32.ShellExecuteExW.return_value = 1  # success
            windll.kernel32.GetProcessId.return_value = pid
            windll.kernel32.WaitForSingleObject.return_value = WAIT_TIMEOUT
            # Capture the SHELLEXECUTEINFO instance via the call to byref.
            captured = {}

            def _sei_side_effect(sei):
                captured["sei"] = sei
                sei.hProcess = hProcess
                return 1
            windll.shell32.ShellExecuteExW.side_effect = _sei_side_effect
            am.launch(idx, command)
        return windll, captured.get("sei")

    def test_lnk_routes_to_shell_execute(self, qapp):
        am = _make_manager()
        windll, _ = self._shell_launch(am, command="C:\\shortcuts\\app.lnk")
        assert windll.shell32.ShellExecuteExW.called

    def test_ms_protocol_routes_to_shell_execute(self, qapp):
        am = _make_manager()
        windll, _ = self._shell_launch(am, command="ms-settings:")
        assert windll.shell32.ShellExecuteExW.called

    def test_emits_app_started_when_no_handle(self, qapp):
        """A UWP/protocol activation with no process handle still announces
        start — running state is tracked via window-matching."""
        am = _make_manager()
        received = []
        am.on_started(lambda e: received.append(e.idx))
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj), \
             patch("infrastructure.windows.catalog.app_manager.ctypes.sizeof", return_value=64), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            windll.shell32.ShellExecuteExW.return_value = 1
            am.launch(5, "ms-settings:")
        assert received == [5]
        # No process registered — running is detected via window-matching.
        assert not am.is_running(5)

    def test_with_handle_registers_process(self, qapp):
        am = _make_manager()
        # Asserts live INSIDE the patch scope: _WinHandle.poll() calls the real
        # WaitForSingleObject once the mock is gone, and the real Win32 call
        # rejects the fake handle 0x200 (WAIT_FAILED), marking the process
        # exited. Keeping the mock active for the duration of the assertions
        # keeps poll() returning None (WAIT_TIMEOUT) as intended.
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj), \
             patch("infrastructure.windows.catalog.app_manager.ctypes.sizeof", return_value=64), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            windll.shell32.ShellExecuteExW.return_value = 1
            windll.kernel32.GetProcessId.return_value = 999
            windll.kernel32.WaitForSingleObject.return_value = WAIT_TIMEOUT

            def _sei(sei):
                sei.hProcess = 0x200
                return 1
            windll.shell32.ShellExecuteExW.side_effect = _sei
            am.launch(2, "C:\\s.lnk")
            assert am.is_running(2)
            assert am.running_pid(2) == 999

    def test_shell_execute_failure_returns_false(self, qapp):
        am = _make_manager()
        failed = []
        am.on_launch_failed(lambda e: failed.append(e.idx))
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj), \
             patch("infrastructure.windows.catalog.app_manager.ctypes.sizeof", return_value=64):
            windll.shell32.ShellExecuteExW.return_value = 0  # failure
            assert am.launch(7, "ms-broken:") is False
        assert failed == [7]


# ── _WinHandle — Win32 process HANDLE wrapper ─────────────────────────────────

class TestWinHandle:
    def test_pid_stored(self):
        h = _WinHandle(hProcess=0x100, pid=4321)
        assert h.pid == 4321
        assert h.returncode is None

    def test_poll_returns_none_when_already_exited(self):
        h = _WinHandle(0x100, 1)
        h.returncode = 0
        assert h.poll() == 0

    def test_poll_returns_none_when_no_handle(self):
        h = _WinHandle(0, 1)
        assert h.poll() is None

    def test_poll_timeout_keeps_none_and_returncode(self):
        h = _WinHandle(0x100, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll:
            windll.kernel32.WaitForSingleObject.return_value = WAIT_TIMEOUT
            assert h.poll() is None
        assert h.returncode is None

    def test_poll_signalled_reads_exit_code_and_closes_handle(self):
        h = _WinHandle(0x100, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj):
            windll.kernel32.WaitForSingleObject.return_value = 0  # signalled

            def _get_exit(handle, ec):
                ec.value = 42
            windll.kernel32.GetExitCodeProcess.side_effect = _get_exit
            assert h.poll() == 42
        assert h.returncode == 42
        windll.kernel32.CloseHandle.assert_called_once()

    def test_wait_blocks_until_signalled(self):
        h = _WinHandle(0x100, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll, \
             patch("infrastructure.windows.catalog.app_manager.ctypes.byref", lambda obj: obj):
            windll.kernel32.WaitForSingleObject.return_value = 0

            def _get_exit(handle, ec):
                ec.value = 7
            windll.kernel32.GetExitCodeProcess.side_effect = _get_exit
            assert h.wait() == 7
        windll.kernel32.WaitForSingleObject.assert_called_once_with(0x100, 0xFFFFFFFF)

    def test_wait_returns_zero_when_no_handle(self):
        h = _WinHandle(0, 1)
        assert h.wait() == 0

    def test_wait_returns_zero_when_already_exited(self):
        h = _WinHandle(0x100, 1)
        h.returncode = 0
        assert h.wait() == 0

    def test_terminate_calls_TerminateProcess(self):
        h = _WinHandle(0x100, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll:
            h.terminate()
        windll.kernel32.TerminateProcess.assert_called_once_with(0x100, 1)

    def test_terminate_noop_when_no_handle(self):
        h = _WinHandle(0, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll:
            h.terminate()
        windll.kernel32.TerminateProcess.assert_not_called()

    def test_kill_aliases_terminate(self):
        h = _WinHandle(0x100, 1)
        with patch("infrastructure.windows.catalog.app_manager.ctypes.windll") as windll:
            h.kill()
        windll.kernel32.TerminateProcess.assert_called_once_with(0x100, 1)


# ── _on_finished ───────────────────────────────────────────────────────────────

class TestOnFinished:
    def test_removes_process(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        am._processes[1] = proc
        am._on_finished(proc, 0)
        assert 1 not in am._processes

    def test_other_processes_remain(self, qapp):
        am = _make_manager()
        ended = _running_proc(pid=100)
        am._processes[0] = ended
        am._processes[1] = _running_proc(pid=200)
        am._on_finished(ended, 0)
        assert 1 in am._processes

    def test_emits_app_finished_with_current_index(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        am._processes[5] = proc
        received = []
        am.on_finished(lambda e: received.append(e.idx))
        am._on_finished(proc, 0)
        assert received == [5]

    def test_noop_for_untracked_process(self, qapp):
        am = _make_manager()
        received = []
        am.on_finished(lambda e: received.append(e.idx))
        am._on_finished(_running_proc(), 0)   # never registered
        assert received == []


# ── terminate / _force_kill ────────────────────────────────────────────────────

class TestTerminate:
    def test_noop_when_not_running(self, qapp):
        am = _make_manager()
        am.terminate(0)   # nie powinno rzucać

    def test_calls_terminate_on_proc(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=1234)
        am._processes[0] = proc
        with patch.object(proc, "terminate") as term, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate(0)
        term.assert_called_once()

    def test_schedules_force_kill_after_3s(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        am._processes[0] = proc
        with patch.object(proc, "terminate"), \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot") as mock_timer:
            am.terminate(0)
        assert mock_timer.call_args[0][0] == 3000

    def test_noop_when_process_already_exited(self, qapp):
        am = _make_manager()
        proc = _exited_proc()
        am._processes[0] = proc
        with patch.object(proc, "terminate") as term:
            am.terminate(0)
        term.assert_not_called()

    def test_terminate_only_affects_target_idx(self, qapp):
        am = _make_manager()
        p0 = _running_proc(pid=100)
        p1 = _running_proc(pid=200)
        am._processes[0] = p0
        am._processes[1] = p1
        with patch.object(p0, "terminate") as t0, \
             patch.object(p1, "terminate") as t1, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate(0)
        t0.assert_called_once()
        t1.assert_not_called()


class TestForceKill:
    def test_calls_kill_when_still_running(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=5678)
        am._processes[0] = proc
        with patch.object(proc, "kill") as kill:
            am._force_kill(proc)
        kill.assert_called_once()

    def test_sends_kill_after_reorder_moved_the_index(self, qapp):
        """A reorder re-keys the process; the force-kill timer (bound to the
        proc, not its old index) must still kill it under its new key."""
        am = _make_manager()
        proc = _running_proc(pid=5678)
        am._processes[3] = proc          # moved here by swap_indices after launch
        with patch.object(proc, "kill") as kill:
            am._force_kill(proc)
        kill.assert_called_once()

    def test_noop_when_process_exited(self, qapp):
        am = _make_manager()
        proc = _exited_proc()
        am._processes[0] = proc
        with patch.object(proc, "kill") as kill:
            am._force_kill(proc)
        kill.assert_not_called()

    def test_noop_when_no_process(self, qapp):
        am = _make_manager()
        proc = _running_proc()   # never registered under any idx
        with patch.object(proc, "kill") as kill:
            am._force_kill(proc)
        kill.assert_not_called()

    def test_noop_when_process_no_longer_tracked(self, qapp):
        """Regression: a close+relaunch swaps in a new process under the same
        idx; the stale force-kill timer scheduled by the previous terminate must
        not kill anything — its target is no longer tracked."""
        am = _make_manager()
        old = _running_proc(pid=1111)    # what terminate() targeted, now gone
        new = _running_proc(pid=4242)    # relaunched under the same idx
        am._processes[0] = new
        with patch.object(old, "kill") as kill_old:
            am._force_kill(old)          # stale timer fires
        kill_old.assert_not_called()


# ── swap_indices (tile reorder) ─────────────────────────────────────────────────

class TestSwapIndices:
    def test_moves_running_process_to_new_index(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=100)
        am._processes[0] = proc
        am.swap_indices(0, 2)
        assert am._processes == {2: proc}
        assert am.running_pid(2) == 100
        assert am.running_pid(0) is None

    def test_exchanges_two_running_processes(self, qapp):
        am = _make_manager()
        p0 = _running_proc(pid=100)
        p1 = _running_proc(pid=200)
        am._processes[0] = p0
        am._processes[1] = p1
        am.swap_indices(0, 1)
        assert am._processes == {0: p1, 1: p0}

    def test_noop_when_neither_index_tracked(self, qapp):
        am = _make_manager()
        am.swap_indices(0, 1)
        assert am._processes == {}


# ── remove_index (tile unpin) ───────────────────────────────────────────────────

class TestRemoveIndex:
    def test_shifts_higher_slots_down(self, qapp):
        am = _make_manager()
        p1 = _running_proc(pid=100)
        p3 = _running_proc(pid=300)
        am._processes[1] = p1
        am._processes[3] = p3
        am.remove_index(2)          # nothing at 2; 3 shifts down to 2
        assert am._processes == {1: p1, 2: p3}

    def test_drops_removed_slot_without_terminating(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=100)
        am._processes[0] = proc
        with patch.object(proc, "terminate") as term:
            am.remove_index(0)
        assert am._processes == {}
        term.assert_not_called()     # unpinned-but-running app keeps running

    def test_removed_then_lower_indices_unchanged(self, qapp):
        am = _make_manager()
        p0 = _running_proc(pid=100)
        p2 = _running_proc(pid=200)
        am._processes[0] = p0
        am._processes[2] = p2
        am.remove_index(1)          # 0 stays, 2 shifts to 1
        assert am._processes == {0: p0, 1: p2}
