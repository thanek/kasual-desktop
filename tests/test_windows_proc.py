"""Tests for the Windows process-tree readers (infrastructure.windows.proc).

These feed the domain game-detection walk (descends_from_launcher), so the key
behaviours are: ppid lookup, and an exe-basename normaliser that lowercases and
strips ``.exe`` so Windows names match the bare launcher set (``Steam.exe`` →
``steam``). A fake ``psutil`` is injected so the tests run with or without the
real package installed.
"""

import sys
import types

import pytest

from infrastructure.windows.proc import parent_pid, process_name


class _NoSuchProcess(Exception):
    pass


def _fake_psutil(monkeypatch, *, name=None, ppid=None, raises=False):
    """Install a fake ``psutil`` module whose Process(pid) yields name()/ppid()."""
    class _Process:
        def __init__(self, pid):
            if raises:
                raise _NoSuchProcess(pid)
        def name(self):
            return name
        def ppid(self):
            return ppid

    mod = types.ModuleType("psutil")
    mod.Process = _Process
    mod.NoSuchProcess = _NoSuchProcess
    monkeypatch.setitem(sys.modules, "psutil", mod)


class TestProcessName:
    def test_strips_exe_and_lowercases(self, monkeypatch):
        _fake_psutil(monkeypatch, name="Steam.exe")
        assert process_name(1234) == "steam"

    def test_uppercase_exe_suffix(self, monkeypatch):
        _fake_psutil(monkeypatch, name="EpicGamesLauncher.EXE")
        assert process_name(1234) == "epicgameslauncher"

    def test_name_without_exe(self, monkeypatch):
        _fake_psutil(monkeypatch, name="System")
        assert process_name(1234) == "system"

    def test_none_when_process_gone(self, monkeypatch):
        _fake_psutil(monkeypatch, raises=True)
        assert process_name(1234) is None

    def test_none_when_name_empty(self, monkeypatch):
        _fake_psutil(monkeypatch, name="")
        assert process_name(1234) is None


class TestParentPid:
    def test_returns_ppid(self, monkeypatch):
        _fake_psutil(monkeypatch, ppid=42)
        assert parent_pid(1234) == 42

    def test_none_when_process_gone(self, monkeypatch):
        _fake_psutil(monkeypatch, raises=True)
        assert parent_pid(1234) is None
