"""
Unit tests for AppManager (Linux multi-process version).

Tests:
  - initial state (is_running, running_app_ids, all_running_pids)
  - launch (creates process, emits app_started)
  - idempotent launch — re-launching a running app_id is ignored
  - launching multiple different apps simultaneously
  - _on_finished (removes from _processes, emits app_finished, other processes intact)
  - terminate(app_id) — SIGTERM + scheduled SIGKILL
  - _force_kill(proc) — SIGKILL only when THIS process is still tracked
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
    sys.platform != "linux",
    reason="Tests the Linux POSIX AppManager; Windows uses WindowsAppManager",
)


def _make_manager():
    from infrastructure.linux.catalog.app_manager import AppManager
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
        assert _make_manager().is_running("a") is False

    def test_running_app_ids_empty(self, qapp):
        assert _make_manager().running_app_ids() == []

    def test_all_running_pids_empty(self, qapp):
        assert _make_manager().all_running_pids() == []


# ── is_running / running_app_ids / running_pid / all_running_pids ─────────────

class TestIsRunning:
    def test_true_for_specific_running_id(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc()
        assert am.is_running("a") is True

    def test_false_for_exited_process(self, qapp):
        am = _make_manager()
        am._processes["a"] = _exited_proc()
        assert am.is_running("a") is False

    def test_false_for_unknown_id(self, qapp):
        am = _make_manager()
        assert am.is_running("unknown") is False

    def test_no_arg_true_when_any_running(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc()
        assert am.is_running() is True

    def test_no_arg_false_when_all_exited(self, qapp):
        am = _make_manager()
        am._processes["a"] = _exited_proc()
        assert am.is_running() is False

    def test_running_app_ids_returns_only_running(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc(pid=1)
        am._processes["b"] = _exited_proc()
        am._processes["c"] = _running_proc(pid=2)
        assert sorted(am.running_app_ids()) == ["a", "c"]

    def test_running_pid_returns_pid(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc(pid=4242)
        assert am.running_pid("a") == 4242

    def test_running_pid_none_when_not_running(self, qapp):
        am = _make_manager()
        assert am.running_pid("a") is None

    def test_running_pid_none_for_exited(self, qapp):
        am = _make_manager()
        am._processes["a"] = _exited_proc()
        assert am.running_pid("a") is None

    def test_all_running_pids(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc(pid=100)
        am._processes["b"] = _running_proc(pid=200)
        am._processes["c"] = _exited_proc()
        assert sorted(am.all_running_pids()) == [100, 200]


# ── launch ─────────────────────────────────────────────────────────────────────

class TestLaunch:
    def _launch(self, am, app_id="a", command="echo", args=None, pid=1234):
        proc = _running_proc(pid=pid)
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch(app_id, command, args or [])
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
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch("a", "echo", [], {"FOO": "bar"})
        env = popen.call_args.kwargs["env"]
        assert env["FOO"] == "bar"
        assert "QT_WAYLAND_SHELL_INTEGRATION" not in env

    def test_media_hw_probe_ban_does_not_leak_into_launched_apps(self, qapp, monkeypatch):
        monkeypatch.setenv("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")
        monkeypatch.setenv("QT_FFMPEG_ENCODING_HW_DEVICE_TYPES", "")
        am = _make_manager()
        popen, _ = self._launch(am)
        env = popen.call_args.kwargs["env"]
        assert "QT_FFMPEG_DECODING_HW_DEVICE_TYPES" not in env
        assert "QT_FFMPEG_ENCODING_HW_DEVICE_TYPES" not in env

    def test_args_converted_to_strings(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="cmd", args=[1, 2, 3])
        assert popen.call_args[0][0] == ["cmd", "1", "2", "3"]

    def test_missing_args_key_defaults_to_empty(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            am.launch("a", "cmd")
        assert popen.call_args[0][0] == ["cmd"]

    def test_emits_app_started(self, qapp):
        am = _make_manager()
        received = []
        am.on_started(lambda e: received.append(e.app_id))
        self._launch(am, app_id="c")
        assert received == ["c"]

    def test_ignored_when_same_id_already_running(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen") as popen:
            am.launch("a", "echo")
        popen.assert_not_called()

    def test_allows_different_ids_simultaneously(self, qapp):
        am = _make_manager()
        self._launch(am, app_id="a", pid=100)
        self._launch(am, app_id="b", pid=200)
        assert sorted(am.running_app_ids()) == ["a", "b"]

    def test_starts_monitor_thread(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", return_value=proc), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread") as mock_thread:
            am.launch("a", "echo")
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_returns_true_on_successful_launch(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", return_value=proc), \
             patch("infrastructure.common.lifecycle.base_app_manager.threading.Thread"):
            assert am.launch("a", "echo") is True

    def test_returns_false_when_already_running(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen"):
            assert am.launch("a", "echo") is False

    def test_returns_false_and_emits_failed_on_missing_command(self, qapp):
        am = _make_manager()
        failed = []
        am.on_launch_failed(lambda e: failed.append((e.app_id, e.error)))
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", side_effect=FileNotFoundError):
            assert am.launch("c", "/no/such/app") is False
        assert failed and failed[0][0] == "c"
        # A failed launch must leave no process registered for that id.
        assert not am.is_running("c")

    def test_returns_false_on_permission_error(self, qapp):
        am = _make_manager()
        with patch("infrastructure.linux.catalog.app_manager.subprocess.Popen", side_effect=PermissionError):
            assert am.launch("a", "/root/secret") is False


# ── _on_finished ───────────────────────────────────────────────────────────────

class TestOnFinished:
    def test_removes_process(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        am._processes["a"] = proc
        am._on_finished(proc, 0)
        assert "a" not in am._processes

    def test_other_processes_remain(self, qapp):
        am = _make_manager()
        ended = _running_proc(pid=100)
        am._processes["a"] = ended
        am._processes["b"] = _running_proc(pid=200)
        am._on_finished(ended, 0)
        assert "b" in am._processes

    def test_emits_app_finished_with_current_id(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        am._processes["e"] = proc
        received = []
        am.on_finished(lambda e: received.append(e.app_id))
        am._on_finished(proc, 0)
        assert received == ["e"]

    def test_noop_for_untracked_process(self, qapp):
        am = _make_manager()
        received = []
        am.on_finished(lambda e: received.append(e.app_id))
        am._on_finished(_running_proc(), 0)   # never registered
        assert received == []


# ── terminate / _force_kill ────────────────────────────────────────────────────

class TestTerminate:
    def test_noop_when_not_running(self, qapp):
        am = _make_manager()
        am.terminate("a")   # nie powinno rzucać

    def test_sends_sigterm(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc(pid=1234)
        with patch("infrastructure.linux.catalog.app_manager.os.getpgid", return_value=1234), \
             patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate("a")
        mock_killpg.assert_called_once_with(1234, signal.SIGTERM)

    def test_schedules_force_kill_after_3s(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc()
        with patch("infrastructure.linux.catalog.app_manager.os.getpgid", return_value=999), \
             patch("infrastructure.linux.catalog.app_manager.os.killpg"), \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot") as mock_timer:
            am.terminate("a")
        assert mock_timer.call_args[0][0] == 3000

    def test_noop_when_process_already_exited(self, qapp):
        am = _make_manager()
        am._processes["a"] = _exited_proc()
        with patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg:
            am.terminate("a")
        mock_killpg.assert_not_called()

    def test_terminate_only_affects_target_id(self, qapp):
        am = _make_manager()
        am._processes["a"] = _running_proc(pid=100)
        am._processes["b"] = _running_proc(pid=200)
        with patch("infrastructure.linux.catalog.app_manager.os.getpgid", return_value=100), \
             patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg, \
             patch("infrastructure.common.lifecycle.base_app_manager.QTimer.singleShot"):
            am.terminate("a")
        mock_killpg.assert_called_once_with(100, signal.SIGTERM)


class TestForceKill:
    def test_sends_sigkill_when_still_running(self, qapp):
        am = _make_manager()
        proc = _running_proc(pid=5678)
        am._processes["a"] = proc
        with patch("infrastructure.linux.catalog.app_manager.os.getpgid", return_value=5678), \
             patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_called_once_with(5678, signal.SIGKILL)

    def test_noop_when_process_exited(self, qapp):
        am = _make_manager()
        proc = _exited_proc()
        am._processes["a"] = proc
        with patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_not_called()

    def test_noop_when_no_process(self, qapp):
        am = _make_manager()
        proc = _running_proc()   # never registered under any id
        with patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg:
            am._force_kill(proc)
        mock_killpg.assert_not_called()

    def test_noop_when_process_no_longer_tracked(self, qapp):
        """Regression: a close+relaunch swaps in a new process under the same
        app id; the stale force-kill timer scheduled by the previous terminate
        must not SIGKILL anything — its target is no longer tracked."""
        am = _make_manager()
        old = _running_proc(pid=1111)    # what terminate() targeted, now gone
        new = _running_proc(pid=4242)    # relaunched under the same id
        am._processes["a"] = new
        with patch("infrastructure.linux.catalog.app_manager.os.getpgid", return_value=1111), \
             patch("infrastructure.linux.catalog.app_manager.os.killpg") as mock_killpg:
            am._force_kill(old)          # stale timer fires
        mock_killpg.assert_not_called()
