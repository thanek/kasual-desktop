"""Starting Kasual Desktop with the system: the choice and the XDG entry."""

import configparser
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain.system.autostart import AutostartChoice
from infrastructure.linux.autostart import XdgAutostart, launcher_for
from infrastructure.linux.compositor import Compositor, build_autostart

_SYSTEMD = "infrastructure.linux.autostart.systemd_runs_autostart_entries"
_LXSESSION = "infrastructure.linux.autostart.lxsession_runs_autostart_entries"


class FakeAutostart:
    def __init__(self, enabled=False):
        self._enabled = enabled
        self.changes = []

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        self.changes.append(enabled)
        self._enabled = enabled


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path / "autostart" / "kasual-desktop.desktop"


def _write(entry, *lines):
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("\n".join(lines))


def _value(entry, key):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(entry)
    return parser["Desktop Entry"][key]


class TestAutostartChoice:
    @pytest.mark.parametrize("enabled", [True, False])
    def test_starts_from_the_current_state(self, enabled):
        assert AutostartChoice(FakeAutostart(enabled)).is_on is enabled

    def test_changes_nothing_until_applied(self):
        autostart = FakeAutostart()
        AutostartChoice(autostart).toggle()
        assert autostart.changes == []

    def test_applies_the_toggled_state(self):
        autostart = FakeAutostart()
        choice = AutostartChoice(autostart)
        choice.toggle()
        choice.apply()
        assert autostart.changes == [True]

    @pytest.mark.parametrize("enabled", [True, False])
    def test_leaves_an_untouched_setting_alone(self, enabled):
        autostart = FakeAutostart(enabled)
        AutostartChoice(autostart).apply()
        assert autostart.changes == []


class TestXdgAutostart:
    def test_is_off_by_default(self, entry):
        assert XdgAutostart("kasual-desktop").is_enabled() is False

    def test_enabling_writes_an_entry_for_the_launcher(self, entry):
        autostart = XdgAutostart("kasual-desktop")
        autostart.set_enabled(True)
        assert autostart.is_enabled() is True
        assert _value(entry, "Exec") == "kasual-desktop"
        assert _value(entry, "TryExec") == "kasual-desktop"

    def test_disabling_removes_the_entry(self, entry):
        autostart = XdgAutostart("kasual-desktop")
        autostart.set_enabled(True)
        autostart.set_enabled(False)
        assert autostart.is_enabled() is False
        assert not entry.exists()

    def test_disabling_twice_is_harmless(self, entry):
        XdgAutostart("kasual-desktop").set_enabled(False)

    def test_a_launcher_path_with_special_characters_is_quoted(self, entry):
        XdgAutostart("/home/me/50% of $games/kasual.sh").set_enabled(True)
        assert _value(entry, "Exec") == '"/home/me/50%% of \\\\$games/kasual.sh"'
        assert _value(entry, "TryExec") == "/home/me/50% of $games/kasual.sh"

    def test_an_entry_added_by_hand_counts_as_enabled(self, entry):
        _write(entry, "[Desktop Entry]", "Exec=kasual-desktop")
        assert XdgAutostart("kasual-desktop").is_enabled() is True

    @pytest.mark.parametrize("line", ["Hidden=true", "X-GNOME-Autostart-enabled=false"])
    def test_an_entry_switched_off_by_the_desktop_counts_as_disabled(self, entry, line):
        _write(entry, "[Desktop Entry]", "Exec=kasual-desktop", line)
        assert XdgAutostart("kasual-desktop").is_enabled() is False

    def test_enabling_brings_back_an_entry_switched_off_by_the_desktop(self, entry):
        _write(entry, "[Desktop Entry]", "Exec=kasual-desktop", "Hidden=true")
        autostart = XdgAutostart("kasual-desktop")
        autostart.set_enabled(True)
        assert autostart.is_enabled() is True

    @pytest.mark.parametrize("content", ["", "garbage", "[Desktop Entry]\nHidden=perhaps"])
    def test_a_malformed_entry_counts_as_disabled(self, entry, content):
        _write(entry, content)
        assert XdgAutostart("kasual-desktop").is_enabled() is False

    def test_an_unwritable_directory_leaves_it_disabled(self, entry):
        entry.parent.write_text("a file where the directory should be")
        autostart = XdgAutostart("kasual-desktop")
        autostart.set_enabled(True)
        assert autostart.is_enabled() is False


class TestLauncher:
    def test_a_checkout_starts_its_own_script(self, tmp_path):
        (tmp_path / "kasual.sh").touch()
        assert launcher_for(tmp_path) == str(tmp_path / "kasual.sh")

    def test_a_package_starts_the_installed_command(self, tmp_path):
        assert launcher_for(tmp_path) == "kasual-desktop"

    def test_the_repository_is_a_checkout(self):
        assert Path(launcher_for(Path(__file__).parent.parent)).name == "kasual.sh"


class TestSessionSupport:
    @pytest.mark.parametrize(
        "compositor", [Compositor.KDE, Compositor.GNOME, Compositor.COSMIC])
    def test_full_desktops_always_offer_it(self, entry, compositor):
        with patch(_SYSTEMD, return_value=False):
            assert build_autostart("kasual-desktop", compositor) is not None

    @pytest.mark.parametrize("compositor", [Compositor.SWAY, Compositor.HYPRLAND])
    @pytest.mark.parametrize("run_by_systemd", [True, False])
    def test_bare_compositors_offer_it_only_when_systemd_runs_entries(
            self, entry, compositor, run_by_systemd):
        with patch(_SYSTEMD, return_value=run_by_systemd):
            offered = build_autostart("kasual-desktop", compositor) is not None
        assert offered is run_by_systemd

    @pytest.mark.parametrize("compositor, offered", [
        (Compositor.LABWC, True), (Compositor.WAYFIRE, True), (Compositor.SWAY, False)])
    def test_lxsession_counts_only_where_raspberry_pi_os_uses_it(
            self, entry, compositor, offered):
        with patch(_SYSTEMD, return_value=False), patch(_LXSESSION, return_value=True):
            assert (build_autostart("kasual-desktop", compositor) is not None) is offered

    def test_an_enabled_entry_can_be_switched_off_in_any_session(self, entry):
        _write(entry, "[Desktop Entry]", "Exec=kasual-desktop")
        with patch(_SYSTEMD, return_value=False):
            assert build_autostart("kasual-desktop", Compositor.SWAY) is not None


class TestFirstRun:
    def _run(self, mock_gamepad, autostart, *events, provisioned=False):
        from session import run_onboarding_or_start
        provisioning, use_case, overlays = MagicMock(), MagicMock(), []
        provisioning.is_provisioned.return_value = provisioned
        use_case.candidates.return_value = []
        start_session = MagicMock()
        run_onboarding_or_start(
            provisioning, use_case, mock_gamepad, MagicMock(), start_session,
            autostart, keep_alive=overlays.append)
        for event in events:
            overlays[0]._handle_pad(event)
        return start_session

    def test_confirming_without_touching_it_leaves_it_off(self, mock_gamepad):
        autostart = FakeAutostart()
        start_session = self._run(mock_gamepad, autostart, "down", "select")
        assert autostart.changes == []
        start_session.assert_called_once_with()

    def test_switching_it_on_takes_effect_on_confirm(self, mock_gamepad):
        autostart = FakeAutostart()
        self._run(mock_gamepad, autostart, "select")
        assert autostart.changes == []
        self._run(mock_gamepad, autostart, "select", "down", "select")
        assert autostart.changes == [True]

    def test_a_session_without_autostart_still_starts(self, mock_gamepad):
        start_session = self._run(mock_gamepad, None, "select")
        start_session.assert_called_once_with()

    def test_later_runs_leave_it_alone(self, mock_gamepad):
        autostart = FakeAutostart()
        start_session = self._run(mock_gamepad, autostart, provisioned=True)
        assert autostart.changes == []
        start_session.assert_called_once_with()
