"""Tests for KdeSystemWallpaper — resolving Plasma's appletsrc to a Wallpaper.

The config path is module-global, so each test points it at a temp file via
monkeypatch; the image files are real temp files (the resolver checks isfile).
"""

import pytest

from domain.shell.wallpaper import Wallpaper
import infrastructure.system.kde_wallpaper as kw
from infrastructure.system.kde_wallpaper import KdeSystemWallpaper


@pytest.fixture
def plasma_cfg(tmp_path, monkeypatch):
    """Return a writer for the appletsrc content, pointing the loader at it."""
    cfg = tmp_path / "plasma-appletsrc"
    monkeypatch.setattr(kw, "_CFG_PATH", cfg)

    def write(body: str) -> None:
        cfg.write_text(body, encoding="utf-8")

    return write


def _wallpaper_section(image: str) -> str:
    return (
        "[Containments][1][Wallpaper][org.kde.image][General]\n"
        f"Image={image}\n"
    )


class TestDirectFile:
    def test_returns_file_path(self, plasma_cfg, tmp_path):
        img = tmp_path / "bg.png"
        img.write_bytes(b"x")
        plasma_cfg(_wallpaper_section(str(img)))
        assert KdeSystemWallpaper().current() == Wallpaper(image_path=str(img))

    def test_strips_file_uri_scheme(self, plasma_cfg, tmp_path):
        img = tmp_path / "bg.png"
        img.write_bytes(b"x")
        plasma_cfg(_wallpaper_section(f"file://{img}"))
        assert KdeSystemWallpaper().current().image_path == str(img)

    def test_missing_file_is_skipped(self, plasma_cfg, tmp_path):
        plasma_cfg(_wallpaper_section(str(tmp_path / "nope.png")))
        assert KdeSystemWallpaper().current() is None


class TestPackage:
    def test_picks_highest_resolution(self, plasma_cfg, tmp_path):
        images = tmp_path / "pkg" / "contents" / "images"
        images.mkdir(parents=True)
        (images / "1920x1080.jpg").write_bytes(b"x")
        (images / "3840x2160.jpg").write_bytes(b"x")
        (images / "800x600.jpg").write_bytes(b"x")
        plasma_cfg(_wallpaper_section(str(tmp_path / "pkg")))
        assert KdeSystemWallpaper().current().image_path.endswith("3840x2160.jpg")

    def test_empty_package_is_skipped(self, plasma_cfg, tmp_path):
        (tmp_path / "pkg" / "contents" / "images").mkdir(parents=True)
        plasma_cfg(_wallpaper_section(str(tmp_path / "pkg")))
        assert KdeSystemWallpaper().current() is None


class TestNoConfig:
    def test_missing_config_returns_none(self, plasma_cfg):
        # writer not called → the temp path does not exist
        assert KdeSystemWallpaper().current() is None

    def test_no_wallpaper_section_returns_none(self, plasma_cfg):
        plasma_cfg("[Containments][1][General]\nfoo=bar\n")
        assert KdeSystemWallpaper().current() is None
