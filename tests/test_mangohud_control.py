"""Tests for MangoHudControl — the HudControl port over MangoHud.conf.

Drives the adapter against a real temp config file, asserting how it reads the
on/off state from `no_display` and how enable/disable rewrite the file.
"""

from pathlib import Path

import pytest

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


class TestState:
    def test_enabled_when_no_no_display(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\ngpu_stats\n")
        assert control.is_enabled() is True

    def test_enabled_when_no_display_commented(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\n# no_display\n")
        assert control.is_enabled() is True

    def test_disabled_with_active_no_display(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\nno_display\n")
        assert control.is_enabled() is False

    def test_disabled_with_no_display_value(self, tmp_path):
        control, _ = _control(tmp_path, "no_display=1\n")
        assert control.is_enabled() is False


class TestEnable:
    def test_comments_out_active_no_display(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\nno_display\n")
        control.enable()
        assert control.is_enabled() is True
        assert "# no_display" in path.read_text()

    def test_preserves_value_when_commenting(self, tmp_path):
        control, path = _control(tmp_path, "no_display=1\n")
        control.enable()
        assert "# no_display=1" in path.read_text()

    def test_no_op_when_already_enabled(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\n")
        control.enable()
        assert path.read_text() == "fps_limit=60\n"  # untouched


class TestDisable:
    def test_appends_no_display_when_absent(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\n")
        control.disable()
        assert control.is_enabled() is False
        assert "no_display" in path.read_text()

    def test_uncomments_existing_no_display(self, tmp_path):
        control, path = _control(tmp_path, "fps_limit=60\n# no_display\n")
        control.disable()
        assert control.is_enabled() is False
        lines = path.read_text().splitlines()
        assert "no_display" in lines  # active, not commented

    def test_no_op_when_already_disabled(self, tmp_path):
        control, path = _control(tmp_path, "no_display\n")
        control.disable()
        assert path.read_text() == "no_display\n"  # untouched


class TestRoundTrip:
    def test_disable_then_enable_returns_enabled(self, tmp_path):
        control, _ = _control(tmp_path, "fps_limit=60\n")
        control.disable()
        assert control.is_enabled() is False
        control.enable()
        assert control.is_enabled() is True
