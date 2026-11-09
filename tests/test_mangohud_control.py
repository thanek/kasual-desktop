"""Tests for MangoHudControl — the HudControl port over MangoHud.conf.

Drives the adapter against a real temp config file, asserting how it reads the
level from `no_display` and `preset=`, and how setting one rewrites the file.
"""

from pathlib import Path

from domain.system.hud import HUD_OFF
from infrastructure.linux.hud.mangohud import MangoHudControl


def _control(tmp_path: Path, contents: str | None) -> tuple[MangoHudControl, Path]:
    path = tmp_path / "MangoHud.conf"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    return MangoHudControl(config_path=path), path


class TestAvailability:
    def test_unavailable_without_file(self, tmp_path):
        control, _ = _control(tmp_path, None)
        assert control.is_available() is False

    def test_available_with_file(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\n")
        assert control.is_available() is True


class TestLaunchEnv:
    def test_arms_the_implicit_vulkan_layer(self, tmp_path):
        """The layer JSON gates itself on MANGOHUD=1; without it, no overlay."""
        control, _ = _control(tmp_path, "fps_limit=60\n")
        assert control.launch_env() == {"MANGOHUD": "1"}


def _set(control: MangoHudControl, value: int) -> None:
    control.set_level(control.level().at(value))


class TestLevel:
    def test_off_with_active_no_display(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\npreset=2\nno_display\n")
        assert control.level().value == HUD_OFF

    def test_off_with_no_display_value(self, tmp_path):
        control, _ = _control(tmp_path, "no_display=1\n")
        assert control.level().value == HUD_OFF

    def test_off_with_the_hiding_preset(self, tmp_path):
        control, _ = _control(tmp_path, "preset=0\n")
        assert control.level().value == HUD_OFF

    def test_reads_the_active_preset(self, tmp_path):
        control, _ = _control(tmp_path, "# no_display\npreset=2\n")
        assert control.level().value == 2

    def test_first_of_a_preset_list(self, tmp_path):
        control, _ = _control(tmp_path, "preset=3,1\n")
        assert control.level().value == 3

    def test_commented_preset_does_not_count(self, tmp_path):
        control, _ = _control(tmp_path, "# preset=1\n")
        assert control.level().value == 4

    def test_own_layout_reads_as_most_detailed(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\ngpu_stats\n")
        assert control.level().value == 4

    def test_default_preset_reads_as_most_detailed(self, tmp_path):
        control, _ = _control(tmp_path, "preset=-1\n")
        assert control.level().value == 4

    def test_offers_mangohuds_four_presets(self, tmp_path):
        control, _ = _control(tmp_path, "")
        assert control.level().most_detailed == 4


class TestSetDetailLevel:
    def test_comments_out_no_display_and_sets_the_preset(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\nno_display=1\n")
        _set(control, 1)
        assert path.read_text() == "fps_limit=60\n# no_display=1\npreset=1\n"

    def test_replaces_the_active_preset_in_place(self, tmp_path):
        control, path = _control(tmp_path, "preset=1\nfps_limit=60\n")
        _set(control, 3)
        assert path.read_text() == "preset=3\nfps_limit=60\n"

    def test_no_op_when_already_there(self, tmp_path):
        control, path = _control(tmp_path, "preset=2\n")
        mtime = path.stat().st_mtime_ns
        _set(control, 2)
        assert path.stat().st_mtime_ns == mtime


class TestSetOff:
    def test_appends_no_display_when_absent(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\npreset=2\n")
        _set(control, HUD_OFF)
        assert path.read_text() == "fps_limit=60\npreset=2\nno_display\n"

    def test_uncomments_existing_no_display(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\n# no_display\n")
        _set(control, HUD_OFF)
        assert "no_display" in path.read_text().splitlines()

    def test_no_op_when_already_off(self, tmp_path):
        control, path = _control(tmp_path, "no_display\n")
        _set(control, HUD_OFF)
        assert path.read_text() == "no_display\n"


class TestAttachment:
    """Whether the layer loaded into the game, read from the environment the
    process was started with."""

    def _attached_to(self, tmp_path, environ, pid=500):
        control = MangoHudControl(config_path=tmp_path / "MangoHud.conf",
                                  environ_of=lambda _pid: environ)
        return control.is_attached(pid)

    def test_attached_when_the_game_carries_the_variable(self, tmp_path):
        assert self._attached_to(tmp_path, {"MANGOHUD": "1"}) is True

    def test_not_attached_without_it(self, tmp_path):
        """What a game started by an already-running launcher comes up with."""
        assert self._attached_to(tmp_path, {"PATH": "/usr/bin"}) is False

    def test_zero_does_not_count(self, tmp_path):
        assert self._attached_to(tmp_path, {"MANGOHUD": "0"}) is False

    def test_kill_switch_wins(self, tmp_path):
        assert self._attached_to(
            tmp_path, {"MANGOHUD": "1", "DISABLE_MANGOHUD": "1"}) is False

    def test_unreadable_process_is_not_attached(self, tmp_path):
        assert self._attached_to(tmp_path, {}) is False

    def test_no_process_is_not_attached(self, tmp_path):
        assert self._attached_to(tmp_path, {"MANGOHUD": "1"}, pid=None) is False


class TestRoundTrip:
    def test_off_then_back_on_restores_the_level(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\n")
        _set(control, 2)
        _set(control, HUD_OFF)
        assert control.level().value == HUD_OFF
        _set(control, 2)
        assert control.level().value == 2
