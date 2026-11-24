"""Autostart through the Run registry key, against an in-memory registry."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
TASK_MANAGER = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run")
SWITCHED_ON, SWITCHED_OFF = b"\x02" + bytes(11), b"\x03" + bytes(11)
NAME = "Kasual Desktop"


class FakeKey:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeRegistry:
    def __init__(self):
        self.keys = {}
        self.read_only = False

    def open(self, _root, path, _reserved=0, _access=0):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return FakeKey(self.keys[path])

    def create(self, _root, path):
        if self.read_only:
            raise PermissionError(path)
        return FakeKey(self.keys.setdefault(path, {}))

    @staticmethod
    def query(key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], 1

    @staticmethod
    def set(key, name, _reserved, _type, value):
        key.values[name] = value

    @staticmethod
    def delete(key, name):
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]


@pytest.fixture
def registry():
    return FakeRegistry()


@pytest.fixture
def adapter(registry, monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=object(), KEY_SET_VALUE=2, REG_SZ=1,
        OpenKey=registry.open, CreateKey=registry.create,
        QueryValueEx=registry.query, SetValueEx=registry.set,
        DeleteValue=registry.delete,
    ))
    monkeypatch.delitem(sys.modules, "infrastructure.windows.autostart", raising=False)
    yield importlib.import_module("infrastructure.windows.autostart")
    sys.modules.pop("infrastructure.windows.autostart", None)


@pytest.fixture
def autostart(adapter):
    return adapter.WindowsAutostart("run kasual")


class TestWindowsAutostart:
    def test_is_off_by_default(self, autostart):
        assert autostart.is_enabled() is False

    def test_enabling_registers_the_command(self, autostart, registry):
        autostart.set_enabled(True)
        assert autostart.is_enabled() is True
        assert registry.keys[RUN] == {NAME: "run kasual"}

    def test_disabling_unregisters_only_kasual_desktop(self, autostart, registry):
        registry.keys[RUN] = {NAME: "run kasual", "Other": "other"}
        autostart.set_enabled(False)
        assert autostart.is_enabled() is False
        assert registry.keys[RUN] == {"Other": "other"}

    def test_disabling_twice_is_harmless(self, autostart):
        autostart.set_enabled(False)

    @pytest.mark.parametrize("state, enabled", [(SWITCHED_ON, True), (SWITCHED_OFF, False)])
    def test_respects_task_manager(self, autostart, registry, state, enabled):
        registry.keys = {RUN: {NAME: "run kasual"}, TASK_MANAGER: {NAME: state}}
        assert autostart.is_enabled() is enabled

    def test_enabling_overrides_task_manager(self, autostart, registry):
        registry.keys = {RUN: {}, TASK_MANAGER: {NAME: SWITCHED_OFF}}
        autostart.set_enabled(True)
        assert autostart.is_enabled() is True

    def test_a_refused_write_leaves_it_disabled(self, autostart, registry):
        registry.read_only = True
        autostart.set_enabled(True)
        assert autostart.is_enabled() is False


class TestCommand:
    def test_runs_without_a_console_when_possible(self, adapter, monkeypatch, tmp_path):
        (tmp_path / "pythonw.exe").touch()
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
        assert adapter.command_running(Path("main.py")) == f"{tmp_path / 'pythonw.exe'} main.py"

    def test_falls_back_to_the_running_interpreter(self, adapter, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
        assert adapter.command_running(Path("main.py")) == f"{tmp_path / 'python.exe'} main.py"

    def test_quotes_paths_with_spaces(self, adapter):
        assert adapter.command_running(Path("my games/main.py")).endswith(
            f'"{Path("my games/main.py")}"')
