"""
Testy jednostkowe dla AppManager.

Testujemy:
  - stan początkowy (is_running, running_idx)
  - launch (tworzy proces, emituje app_started, ignoruje gdy już działa)
  - _on_finished (resetuje stan, emituje app_finished)
  - terminate (_killpg SIGTERM, harmonogram _force_kill)
  - _force_kill (SIGKILL gdy proces jeszcze żyje, noop gdy zakończony)

Subprocess.Popen i threading.Thread są zawsze mockowane — testy nie
uruchamiają żadnych prawdziwych procesów ani wątków.
"""

import signal
from unittest.mock import MagicMock, patch


def _make_manager():
    from app_manager import AppManager
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

    def test_running_idx_none(self, qapp):
        assert _make_manager().running_idx() is None


# ── is_running / running_idx ───────────────────────────────────────────────────

class TestIsRunning:
    def test_true_when_process_alive(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 0
        assert am.is_running() is True

    def test_false_when_process_exited(self, qapp):
        am = _make_manager()
        am._process = _exited_proc()
        am._running_idx = 0
        assert am.is_running() is False

    def test_false_when_no_process(self, qapp):
        am = _make_manager()
        assert am.is_running() is False

    def test_running_idx_returns_idx_when_alive(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 7
        assert am.running_idx() == 7

    def test_running_idx_none_when_exited(self, qapp):
        am = _make_manager()
        am._process = _exited_proc()
        am._running_idx = 7
        assert am.running_idx() is None


# ── launch ─────────────────────────────────────────────────────────────────────

class TestLaunch:
    def _launch(self, am, idx=0, command="echo", args=None):
        proc = _running_proc()
        with patch("app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("app_manager.threading.Thread"):
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
        with patch("app_manager.subprocess.Popen", return_value=proc) as popen, \
             patch("app_manager.threading.Thread"):
            am.launch(0, {"command": "cmd"})
        assert popen.call_args[0][0] == ["cmd"]

    def test_emits_app_started(self, qapp):
        am = _make_manager()
        received = []
        am.app_started.connect(lambda idx: received.append(idx))
        self._launch(am, idx=3)
        assert received == [3]

    def test_ignored_when_already_running(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 0
        with patch("app_manager.subprocess.Popen") as popen:
            am.launch(1, {"command": "echo"})
        popen.assert_not_called()

    def test_starts_monitor_thread(self, qapp):
        am = _make_manager()
        proc = _running_proc()
        with patch("app_manager.subprocess.Popen", return_value=proc), \
             patch("app_manager.threading.Thread") as mock_thread:
            am.launch(0, {"command": "echo"})
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


# ── _on_finished ───────────────────────────────────────────────────────────────

class TestOnFinished:
    def test_resets_process(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 1
        am._on_finished(1, 0)
        assert am._process is None

    def test_resets_running_idx(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 1
        am._on_finished(1, 0)
        assert am._running_idx is None

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
        am.terminate()   # nie powinno rzucać

    def test_sends_sigterm(self, qapp):
        am = _make_manager()
        am._process = _running_proc(pid=1234)
        am._running_idx = 0
        with patch("app_manager.os.getpgid", return_value=1234), \
             patch("app_manager.os.killpg") as mock_killpg, \
             patch("app_manager.QTimer.singleShot"):
            am.terminate()
        mock_killpg.assert_called_once_with(1234, signal.SIGTERM)

    def test_schedules_force_kill_after_3s(self, qapp):
        am = _make_manager()
        am._process = _running_proc()
        am._running_idx = 0
        with patch("app_manager.os.getpgid", return_value=999), \
             patch("app_manager.os.killpg"), \
             patch("app_manager.QTimer.singleShot") as mock_timer:
            am.terminate()
        mock_timer.assert_called_once_with(3000, am._force_kill)

    def test_noop_when_process_already_exited(self, qapp):
        am = _make_manager()
        am._process = _exited_proc()
        am._running_idx = 0
        with patch("app_manager.os.killpg") as mock_killpg:
            am.terminate()
        mock_killpg.assert_not_called()


class TestForceKill:
    def test_sends_sigkill_when_still_running(self, qapp):
        am = _make_manager()
        am._process = _running_proc(pid=5678)
        am._running_idx = 0
        with patch("app_manager.os.getpgid", return_value=5678), \
             patch("app_manager.os.killpg") as mock_killpg:
            am._force_kill()
        mock_killpg.assert_called_once_with(5678, signal.SIGKILL)

    def test_noop_when_process_exited(self, qapp):
        am = _make_manager()
        am._process = _exited_proc()
        am._running_idx = 0
        with patch("app_manager.os.killpg") as mock_killpg:
            am._force_kill()
        mock_killpg.assert_not_called()

    def test_noop_when_no_process(self, qapp):
        am = _make_manager()
        with patch("app_manager.os.killpg") as mock_killpg:
            am._force_kill()
        mock_killpg.assert_not_called()
