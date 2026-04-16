"""
Testy jednostkowe dla AppManager (wersja multi-process).

Testujemy:
  - stan początkowy (is_running, running_idxs, all_running_pids)
  - launch (tworzy proces, emituje app_started)
  - launch idempotentny — ponowne uruchomienie działającego idx jest ignorowane
  - launch wielu różnych aplikacji jednocześnie
  - _on_finished (usuwa z _processes, emituje app_finished, inne procesy nienaruszone)
  - terminate(idx) — SIGTERM + harmonogram SIGKILL
  - _force_kill(idx)
  - running_pid / all_running_pids / is_running

Subprocess.Popen i threading.Thread są zawsze mockowane — testy nie
uruchamiają żadnych prawdziwych procesów ani wątków.
"""

import signal
from unittest.mock import MagicMock, patch


def _make_manager():
    from system.app_manager import AppManager
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
        with patch("system.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("system.app_manager.threading.Thread"):
            am.launch(idx, {"command": command, "args": args or []})
        return popen, proc

    def test_creates_process_with_correct_command(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="echo", args=["hello"])
        popen.assert_called_once_with(["echo", "hello"], start_new_session=True)

    def test_args_converted_to_strings(self, qapp):
        am = _make_manager()
        popen, _ = self._launch(am, command="cmd", args=[1, 2, 3])
        assert popen.call_args[0][0] == ["cmd", "1", "2", "3"]

    def test_missing_args_key_defaults_to_empty(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("system.app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("system.app_manager.threading.Thread"):
            am.launch(0, {"command": "cmd"})
        assert popen.call_args[0][0] == ["cmd"]

    def test_emits_app_started(self, qapp):
        am = _make_manager()
        received = []
        am.app_started.connect(lambda idx: received.append(idx))
        self._launch(am, idx=3)
        assert received == [3]

    def test_ignored_when_same_idx_already_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("system.app_manager.subprocess.Popen") as popen:
            am.launch(0, {"command": "echo"})
        popen.assert_not_called()

    def test_allows_different_idxs_simultaneously(self, qapp):
        am = _make_manager()
        self._launch(am, idx=0, pid=100)
        self._launch(am, idx=1, pid=200)
        assert sorted(am.running_idxs()) == [0, 1]

    def test_starts_monitor_thread(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("system.app_manager.subprocess.Popen", return_value=proc), \
             patch("system.app_manager.threading.Thread") as mock_thread:
            am.launch(0, {"command": "echo"})
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


# ── _on_finished ───────────────────────────────────────────────────────────────

class TestOnFinished:
    def test_removes_process(self, qapp):
        am = _make_manager()
        am._processes[1] = _running_proc()
        am._on_finished(1, 0)
        assert 1 not in am._processes

    def test_other_processes_remain(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=100)
        am._processes[1] = _running_proc(pid=200)
        am._on_finished(0, 0)
        assert 1 in am._processes

    def test_emits_app_finished(self, qapp):
        am = _make_manager()
        received = []
        am.app_finished.connect(lambda idx: received.append(idx))
        am._on_finished(5, 0)
        assert received == [5]


# ── terminate / _force_kill ────────────────────────────────────────────────────

class TestTerminate:
    def test_noop_when_not_running(self, qapp):
        am = _make_manager()
        am.terminate(0)   # nie powinno rzucać

    def test_sends_sigterm(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=1234)
        with patch("system.app_manager.os.getpgid", return_value=1234), \
             patch("system.app_manager.os.killpg") as mock_killpg, \
             patch("system.app_manager.QTimer.singleShot"):
            am.terminate(0)
        mock_killpg.assert_called_once_with(1234, signal.SIGTERM)

    def test_schedules_force_kill_after_3s(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc()
        with patch("system.app_manager.os.getpgid", return_value=999), \
             patch("system.app_manager.os.killpg"), \
             patch("system.app_manager.QTimer.singleShot") as mock_timer:
            am.terminate(0)
        assert mock_timer.call_args[0][0] == 3000

    def test_noop_when_process_already_exited(self, qapp):
        am = _make_manager()
        am._processes[0] = _exited_proc()
        with patch("system.app_manager.os.killpg") as mock_killpg:
            am.terminate(0)
        mock_killpg.assert_not_called()

    def test_terminate_only_affects_target_idx(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=100)
        am._processes[1] = _running_proc(pid=200)
        with patch("system.app_manager.os.getpgid", return_value=100), \
             patch("system.app_manager.os.killpg") as mock_killpg, \
             patch("system.app_manager.QTimer.singleShot"):
            am.terminate(0)
        mock_killpg.assert_called_once_with(100, signal.SIGTERM)


class TestForceKill:
    def test_sends_sigkill_when_still_running(self, qapp):
        am = _make_manager()
        am._processes[0] = _running_proc(pid=5678)
        with patch("system.app_manager.os.getpgid", return_value=5678), \
             patch("system.app_manager.os.killpg") as mock_killpg:
            am._force_kill(0)
        mock_killpg.assert_called_once_with(5678, signal.SIGKILL)

    def test_noop_when_process_exited(self, qapp):
        am = _make_manager()
        am._processes[0] = _exited_proc()
        with patch("system.app_manager.os.killpg") as mock_killpg:
            am._force_kill(0)
        mock_killpg.assert_not_called()

    def test_noop_when_no_process(self, qapp):
        am = _make_manager()
        with patch("system.app_manager.os.killpg") as mock_killpg:
            am._force_kill(0)
        mock_killpg.assert_not_called()
