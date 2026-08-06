"""Tests for the JSON-backed scalar preferences (DesktopPowerPreference)."""

import json

import pytest

from domain.system.actions import SLEEP, RESTART, SHUTDOWN
from infrastructure.common.catalog.preferences import (
    DesktopBackgroundHintMemory, DesktopPowerPreference,
)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point the preferences store at a temp config root."""
    monkeypatch.setattr(
        "infrastructure.common.catalog.preferences.config_root", lambda: tmp_path)
    return tmp_path


class TestDefault:
    def test_falls_back_to_sleep_when_unset(self, cfg):
        assert DesktopPowerPreference().default() == SLEEP

    def test_reads_persisted_value(self, cfg):
        (cfg / "preferences.json").write_text(json.dumps({"power_default": RESTART}))
        assert DesktopPowerPreference().default() == RESTART

    def test_ignores_non_power_value(self, cfg):
        (cfg / "preferences.json").write_text(json.dumps({"power_default": "volume"}))
        assert DesktopPowerPreference().default() == SLEEP

    def test_falls_back_on_corrupt_file(self, cfg):
        (cfg / "preferences.json").write_text("{not json")
        assert DesktopPowerPreference().default() == SLEEP


class TestSetDefault:
    def test_persists_and_reads_back(self, cfg):
        DesktopPowerPreference().set_default(SHUTDOWN)
        assert DesktopPowerPreference().default() == SHUTDOWN
        assert json.loads((cfg / "preferences.json").read_text())["power_default"] == SHUTDOWN

    def test_creates_config_dir_if_missing(self, tmp_path, monkeypatch):
        nested = tmp_path / "a" / "b"
        monkeypatch.setattr(
            "infrastructure.common.catalog.preferences.config_root", lambda: nested)
        DesktopPowerPreference().set_default(RESTART)
        assert (nested / "preferences.json").is_file()

    def test_ignores_invalid_action(self, cfg):
        DesktopPowerPreference().set_default("brightness")
        assert not (cfg / "preferences.json").exists()

    def test_preserves_other_keys(self, cfg):
        (cfg / "preferences.json").write_text(json.dumps({"other": 1}))
        DesktopPowerPreference().set_default(RESTART)
        data = json.loads((cfg / "preferences.json").read_text())
        assert data == {"other": 1, "power_default": RESTART}


class TestBackgroundHintMemory:
    def test_unshown_until_marked(self, cfg):
        assert DesktopBackgroundHintMemory().was_ever_shown() is False

    def test_the_mark_outlives_the_process(self, cfg):
        DesktopBackgroundHintMemory().mark_shown()
        assert DesktopBackgroundHintMemory().was_ever_shown() is True

    def test_shares_the_file_with_the_power_default(self, cfg):
        DesktopPowerPreference().set_default(RESTART)
        DesktopBackgroundHintMemory().mark_shown()
        data = json.loads((cfg / "preferences.json").read_text())
        assert data == {"power_default": RESTART, "background_hint_shown": True}
