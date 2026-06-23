"""
Unit tests for AppManager (Linux multi-process version).

Tests:
  - initial state (is_running, running_idxs, all_running_pids)
  - launch (creates process, emits app_started)
  - idempotent launch — re-launching a running idx is ignored
  - launching multiple different apps simultaneously
  - _on_finished (removes from _processes, emits app_finished, other processes intact)
  - terminate(idx) — SIGTERM + scheduled SIGKILL
  - _force_kill(proc) — SIGKILL only when THIS process is still tracked
  - swap_indices — moves tracked process after tile order change
  - running_pid / all_running_pids / is_running

Subprocess.Popen and threading.Thread are always mocked — tests don't
start any real processes or threads. Skipped on Windows — Windows uses
WindowsAppManager (ShellExecuteEx/subprocess) with its own behaviour.
"""

import signal
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Tests the Linux POSIX AppManager; Windows uses WindowsAppManager",
)


def _make_manager():
    from infrastructure.kde.app_manager import AppManager
    return AppManager()


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


# ── launch ─────────────────────────────────────────────────────────────────────

class TestLaunch:
    def _launch(self, am, idx=0, command="echo", args=None, pid=1234):
        proc = _running_proc(pid=pid)
        with patch("infrastructure.kde.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(idx, command, args or [])
        return popen, proc

    def test_creates_process_with_correct_command(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="echo", args=["hello"])
        args, kwargs = popen.call_args
        assert args[0] == ["echo", "hello"]
        assert kwargs["start_new_session"] is True
        # Our layer-shell integration must not leak into launched apps.
        assert "QT_WAYLAND_SHELL_INTEGRATION" not in kwargs["env"]

    def test_env_merges_app_env(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=1234)
        with patch("infrastructure.kde.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(0, "echo", [], {"FOO": "bar"})
        env = popen.call_args.kwargs["env"]
        assert env["FOO"] == "bar"
        assert "QT_WAYLAND_SHELL_INTEGRATION" not in env

    def test_args_converted_to_strings(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="cmd", args=[1, 2, 3])
        assert popen.call_args[0][0] == ["cmd", "1", "2", "3"]

    def test_missing_args_key_defaults_to_empty(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.kde.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(0, "cmd")
        assert popen.call_args[0][0] == ["cmd"]

    def test_emits_app_started(self, qapp):
        am = _make_manager()
        received = []
        am.on_started(lambda e: received.append(e.idx))
        self._launch(am, idx=3)
        assert received == [3]

    def test_ignored_when_same_idx_already_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("infrastructure.kde.app_manager.subprocess.Popen") as popen:
            am.launch(0, "echo")
        popen.assert_not_called()

    def test_allows_different_idxs_simultaneously(self, qapp):
        am = _make_manager()
        self._launch(am, idx=0, pid=100)
        self._launch(am, idx=1, pid=200)
        assert sorted(am.running_idxs()) == [0, 1]

    def test_starts_monitor_thread(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.kde.app_manager.subprocess.Popen", return_value=proc), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread") as mock_thread:
            am.launch(0, "echo")
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_returns_true_on_successful_launch(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.kde.app_manager.subprocess.Popen", return_value=proc), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            assert am.launch(0, "echo") is True

    def test_returns_false_when_already_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("infrastructure.kde.app_manager.subprocess.Popen"):
            assert am.launch(0, "echo") is False

    def test_returns_false_and_emits_failed_on_missing_command(self, qapp):
        am = _make_manager()
        failed = []
        am.on_launch_failed(lambda e: failed.append((e.idx, e.error)))
        with patch("infrastructure.kde.app_manager.subprocess.Popen", side_effect=FileNotFoundError):
            assert am.launch(2, "/no/such/app") is False
        assert failed and failed[0][0] == 2
        # A failed launch must leave no process registered for that idx.
        assert not am.is_running(2)

    def test_returns_false_on_permission_error(self, qapp):
        am = _make_manager()
        with patch("infrastructure.kde.app_manager.subprocess.Popen", side_effect=PermissionError):
            assert am.launch(0, "/root/secret") is False


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

    def test_sends_sigterm(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=1234)
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=1234), \
             patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate(0)
        mock_killpg.assert_called_once_with(1234, signal.SIGTERM)

    def test_schedules_force_kill_after_3s(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=999), \
             patch("infrastructure.kde.app_manager.os.killpg"), \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot") as mock_timer:
            am.terminate(0)
        assert mock_timer.call_args[0][0] == 3000

    def test_noop_when_process_already_exited(self, qapp):
        am = _make_manager()
        am._processes[0] = _exited_proc()
        with patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am.terminate(0)
        mock_killpg.assert_not_called()

    def test_terminate_only_affects_target_idx(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=100)
        am._processes[1] = _running_proc(pid=200)
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=100), \
             patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate(0)
        mock_killpg.assert_called_once_with(100, signal.SIGTERM)


class TestForceKill:
    def test_sends_sigkill_when_still_running(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=5678)
        am._processes[0] = proc
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=5678), \
             patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_called_once_with(5678, signal.SIGKILL)

    def test_sends_sigkill_after_reorder_moved_the_index(self, qapp):
        """A reorder re-keys the process; the force-kill timer (bound to the proc,
        not its old index) must still SIGKILL it under its new key."""
        am = _make_manager()
        proc = _running_proc(pid=5678)
        am._processes[3] = proc          # moved here by swap_indices after launch
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=5678), \
             patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_called_once_with(5678, signal.SIGKILL)

    def test_noop_when_process_exited(self, qapp):
        am = _make_manager()
        proc = _exited_proc()
        am._processes[0] = proc
        with patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_not_called()

    def test_noop_when_no_process(self, qapp):
        am = _make_manager()
        proc = _running_proc()   # never registered under any idx
        with patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_not_called()

    def test_noop_when_process_no_longer_tracked(self, qapp):
        """Regression: a close+relaunch swaps in a new process under the same
        idx; the stale force-kill timer scheduled by the previous terminate must
        not SIGKILL anything — its target is no longer tracked."""
        am = _make_manager()
        old = _running_proc(pid=1111)    # what terminate() targeted, now gone
        new = _running_proc(pid=4242)    # relaunched under the same idx
        am._processes[0] = new
        with patch("infrastructure.kde.app_manager.os.getpgid", return_value=1111), \
             patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am._force_kill(old)          # stale timer fires
        mock_killpg.assert_not_called()


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
        with patch("infrastructure.kde.app_manager.os.killpg") as mock_killpg:
            am.remove_index(0)
        assert am._processes == {}
        mock_killpg.assert_not_called()     # unpinned-but-running app keeps running

    def test_removed_then_lower_indices_unchanged(self, qapp):
        am = _make_manager()
        p0 = _running_proc(pid=100)
        p2 = _running_proc(pid=200)
        am._processes[0] = p0
        am._processes[2] = p2
        am.remove_index(1)          # 0 stays, 2 shifts to 1
        assert am._processes == {0: p0, 1: p2}
