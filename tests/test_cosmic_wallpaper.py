"""Tests for the COSMIC wallpaper adapter, which reads cosmic-config off disk.

The config layering is faked with tmp dirs: XDG_CONFIG_HOME stands for the user's
own settings and XDG_DATA_DIRS for the system defaults underneath them.
"""

from pathlib import Path

import pytest

from infrastructure.cosmic.display.wallpaper import CosmicSystemWallpaper

_COMPONENT = "cosmic/com.system76.CosmicBackground/v1"


def _entry(source: str) -> str:
    return (f'(\n    output: "all",\n    source: {source},\n'
            '    filter_by_theme: true,\n    rotation_frequency: 3600,\n)\n')


def _write(base: Path, key: str, value: str) -> None:
    path = base / _COMPONENT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _image(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / name
    image.write_bytes(b"\x89PNG\r\n")
    return image


@pytest.fixture
def cosmic_config(tmp_path, monkeypatch):
    """User config over system defaults, with no static-file fallback in reach."""
    user, system = tmp_path / "config", tmp_path / "data"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user))
    monkeypatch.setenv("XDG_DATA_DIRS", str(system))
    return user, system


class TestCosmicSystemWallpaper:
    def test_reads_the_configured_image(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        image = _image(tmp_path / "pics", "wall.png")
        _write(user, "all", _entry(f'Path("{image}")'))
        assert CosmicSystemWallpaper().current().image_path == str(image)

    def test_user_config_wins_over_system_default(self, cosmic_config, tmp_path):
        user, system = cosmic_config
        chosen = _image(tmp_path / "pics", "chosen.png")
        shipped = _image(tmp_path / "pics", "shipped.png")
        _write(system, "all", _entry(f'Path("{shipped}")'))
        _write(user, "all", _entry(f'Path("{chosen}")'))
        assert CosmicSystemWallpaper().current().image_path == str(chosen)

    def test_falls_back_to_system_default(self, cosmic_config, tmp_path):
        _, system = cosmic_config
        shipped = _image(tmp_path / "pics", "shipped.png")
        _write(system, "all", _entry(f'Path("{shipped}")'))
        assert CosmicSystemWallpaper().current().image_path == str(shipped)

    def test_directory_source_takes_the_first_image(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        slideshow = tmp_path / "slideshow"
        _image(slideshow, "b.png")
        first = _image(slideshow, "a.jpg")
        (slideshow / "notes.txt").write_text("ignored")
        _write(user, "all", _entry(f'Path("{slideshow}")'))
        assert CosmicSystemWallpaper().current().image_path == str(first)

    def test_colour_source_has_no_image(self, cosmic_config):
        user, _ = cosmic_config
        _write(user, "all", _entry("Color(Single((0.1, 0.2, 0.3)))"))
        assert CosmicSystemWallpaper().current() is None

    def test_missing_file_is_not_offered(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        _write(user, "all", _entry(f'Path("{tmp_path / "gone.png"}")'))
        assert CosmicSystemWallpaper().current() is None

    def test_no_config_at_all(self, cosmic_config):
        assert CosmicSystemWallpaper().current() is None


class TestPerOutputEntries:
    def test_per_output_entry_used_when_outputs_differ(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        shared = _image(tmp_path / "pics", "shared.png")
        per_output = _image(tmp_path / "pics", "dp1.png")
        _write(user, "same-on-all", "false\n")
        _write(user, "backgrounds", '[Output("DP-1")]\n')
        _write(user, "output.DP-1", _entry(f'Path("{per_output}")'))
        _write(user, "all", _entry(f'Path("{shared}")'))
        assert CosmicSystemWallpaper().current().image_path == str(per_output)

    def test_shared_entry_backs_up_an_output_without_one(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        shared = _image(tmp_path / "pics", "shared.png")
        _write(user, "same-on-all", "false\n")
        _write(user, "backgrounds", '[Output("DP-9")]\n')
        _write(user, "all", _entry(f'Path("{shared}")'))
        assert CosmicSystemWallpaper().current().image_path == str(shared)

    def test_same_on_all_ignores_per_output_entries(self, cosmic_config, tmp_path):
        user, _ = cosmic_config
        shared = _image(tmp_path / "pics", "shared.png")
        per_output = _image(tmp_path / "pics", "dp1.png")
        _write(user, "same-on-all", "true\n")
        _write(user, "backgrounds", '[Output("DP-1")]\n')
        _write(user, "output.DP-1", _entry(f'Path("{per_output}")'))
        _write(user, "all", _entry(f'Path("{shared}")'))
        assert CosmicSystemWallpaper().current().image_path == str(shared)
