"""Tests for the JSON-backed scalar preferences."""

import json

import pytest

from domain.system.actions import SLEEP, RESTART, SHUTDOWN
from domain.audio.output import AudioOutput
from infrastructure.common.catalog.preferences import (
    DesktopBackgroundHintMemory, DesktopBorrowedOutputMemory, DesktopDisplayPreference,
    DesktopOutputPreference, DesktopPowerPreference,
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


class TestDisplayPreference:
    def test_the_system_decides_when_unset(self, cfg):
        assert DesktopDisplayPreference().preferred() is None

    def test_persists_and_reads_back(self, cfg):
        DesktopDisplayPreference().set_preferred("HDMI-A-1")
        assert DesktopDisplayPreference().preferred() == "HDMI-A-1"

    def test_clearing_returns_the_choice_to_the_system(self, cfg):
        DesktopDisplayPreference().set_preferred("HDMI-A-1")
        DesktopDisplayPreference().set_preferred(None)
        assert DesktopDisplayPreference().preferred() is None

    def test_keeps_the_other_preferences(self, cfg):
        DesktopPowerPreference().set_default(SHUTDOWN)
        DesktopDisplayPreference().set_preferred("DP-1")
        assert DesktopPowerPreference().default() == SHUTDOWN

    def test_ignores_a_value_that_names_no_screen(self, cfg):
        (cfg / "preferences.json").write_text(json.dumps({"display": 3}))
        assert DesktopDisplayPreference().preferred() is None


HDMI = AudioOutput("alsa_card.pci-0000_01_00.1:hdmi-output-0", "HDMI/DisplayPort – SAMSUNG")


class TestOutputPreference:
    def test_the_system_decides_when_unset(self, cfg):
        assert DesktopOutputPreference().preferred() is None

    def test_persists_the_output_with_its_label(self, cfg):
        DesktopOutputPreference().set_preferred(HDMI)
        assert DesktopOutputPreference().preferred() == HDMI

    def test_clearing_returns_the_choice_to_the_system(self, cfg):
        DesktopOutputPreference().set_preferred(HDMI)
        DesktopOutputPreference().set_preferred(None)
        assert DesktopOutputPreference().preferred() is None

    def test_keeps_the_other_preferences(self, cfg):
        DesktopPowerPreference().set_default(RESTART)
        DesktopOutputPreference().set_preferred(HDMI)
        assert DesktopPowerPreference().default() == RESTART


class TestBorrowedOutputMemory:
    def test_nothing_borrowed_until_remembered(self, cfg):
        assert DesktopBorrowedOutputMemory().borrowed_from_system() is None

    def test_the_loan_outlives_the_process(self, cfg):
        DesktopBorrowedOutputMemory().remember_borrowed_from_system("usb:speaker")
        assert DesktopBorrowedOutputMemory().borrowed_from_system() == "usb:speaker"

    def test_forgetting_clears_it(self, cfg):
        DesktopBorrowedOutputMemory().remember_borrowed_from_system("usb:speaker")
        DesktopBorrowedOutputMemory().remember_borrowed_from_system(None)
        assert DesktopBorrowedOutputMemory().borrowed_from_system() is None
