"""Tests for LogViewerLauncher — spawning the log viewer as its own process.

No Qt here: the launcher is pure process management. A fake ``popen`` records the
spawn command and environment and yields a controllable fake process.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pathlib import Path

from infrastructure.kde.log.log_viewer_launcher import LogViewerLauncher


class _FakeProc:
    def __init__(self) -> None:
        self._alive = True
        self.terminated = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False

    def exit(self) -> None:
        """Simulate the process ending on its own."""
        self._alive = False


class _FakePopen:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.procs: list[_FakeProc] = []

    def __call__(self, cmd, env=None):
        self.calls.append((cmd, env))
        proc = _FakeProc()
        self.procs.append(proc)
        return proc


_ENTRY = Path("/somewhere/src/log_viewer_main.py")
_LOG = "/tmp/kasual.log"


def _make():
    popen = _FakePopen()
    return LogViewerLauncher(log_file=_LOG, entry=_ENTRY, popen=popen), popen


class TestOpen:
    def test_spawns_child_without_layer_shell_env(self, monkeypatch):
        monkeypatch.setenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")
        monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
        launcher, popen = _make()

        launcher.open()

        assert len(popen.calls) == 1
        cmd, env = popen.calls[0]
        assert cmd == [sys.executable, str(_ENTRY), _LOG]
        # The layer-shell integration must NOT leak into the child …
        assert "QT_WAYLAND_SHELL_INTEGRATION" not in env
        # … but the rest of the environment is preserved.
        assert env["QT_QPA_PLATFORM"] == "wayland"

    def test_single_instance_while_alive(self):
        launcher, popen = _make()
        launcher.open()
        launcher.open()
        assert len(popen.calls) == 1

    def test_respawns_after_child_exits(self):
        launcher, popen = _make()
        launcher.open()
        popen.procs[0].exit()
        launcher.open()
        assert len(popen.calls) == 2


class TestClose:
    def test_terminates_running_child(self):
        launcher, popen = _make()
        launcher.open()
        launcher.close()
        assert popen.procs[0].terminated is True

    def test_noop_when_never_opened(self):
        launcher, _ = _make()
        launcher.close()  # must not raise

    def test_noop_when_child_already_exited(self):
        launcher, popen = _make()
        launcher.open()
        popen.procs[0].exit()
        launcher.close()
        assert popen.procs[0].terminated is False
