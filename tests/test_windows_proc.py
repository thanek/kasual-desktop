"""Tests for infrastructure.windows.proc — psutil-backed parent-PID lookup.

A fake ``psutil`` is injected so the tests run with or without the real
package installed.
"""

import sys
import types

from infrastructure.windows.proc import parent_pid


class _NoSuchProcess(Exception):
    pass


def _fake_psutil(monkeypatch, *, ppid=None, raises=False):
    """Install a fake ``psutil`` module whose Process(pid) yields ppid()."""
    class _Process:
        def __init__(self, pid):
            if raises:
                raise _NoSuchProcess(pid)
        def ppid(self):
            return ppid

    mod = types.ModuleType("psutil")
    mod.Process = _Process
    mod.NoSuchProcess = _NoSuchProcess
    monkeypatch.setitem(sys.modules, "psutil", mod)


class TestParentPid:
    def test_returns_ppid(self, monkeypatch):
        _fake_psutil(monkeypatch, ppid=42)
        assert parent_pid(1234) == 42

    def test_none_when_process_gone(self, monkeypatch):
        _fake_psutil(monkeypatch, raises=True)
        assert parent_pid(1234) is None
