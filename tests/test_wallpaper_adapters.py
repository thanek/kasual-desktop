"""Tests for the non-Plasma wallpaper adapters: the static file fallback, the
pcmanfm desktop (Raspberry Pi OS) and the Sway/Hyprland/Wayfire compositor
sources (all resolved fresh per Kasual Desktop launch)."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.linux.display.wallpaper import PcmanfmWallpaper, StaticFileWallpaper
from infrastructure.wlroots.display.wallpaper import (
    HyprlandWallpaper, SwayWallpaper, WayfireWallpaper,
)


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _image(tmp_path, name="wall.png"):
    img = tmp_path / name
    img.write_bytes(b"\x89PNG\r\n")
    return img


# ── StaticFileWallpaper ──────────────────────────────────────────────────────

class TestStaticFileWallpaper:
    def test_none_when_absent(self, config_home):
        assert StaticFileWallpaper().current() is None

    def test_returns_configured_file(self, config_home, tmp_path):
        img = _image(tmp_path)
        (config_home / "kasual-desktop").mkdir()
        (config_home / "kasual-desktop" / "wallpaper").symlink_to(img)
        result = StaticFileWallpaper().current()
        assert result is not None
        assert result.image_path.endswith("wallpaper")

    def test_none_when_path_is_a_directory(self, config_home):
        (config_home / "kasual-desktop").mkdir()
        (config_home / "kasual-desktop" / "wallpaper").mkdir()
        assert StaticFileWallpaper().current() is None


# ── HyprlandWallpaper ────────────────────────────────────────────────────────

class TestHyprlandWallpaper:
    def test_returns_active_wallpaper(self, config_home, tmp_path):
        img = _image(tmp_path)
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run") as run:
            run.return_value.stdout = f"eDP-1 = {img}\n"
            result = HyprlandWallpaper().current()
        assert result.image_path == str(img)

    def test_returns_swww_wallpaper(self, config_home, tmp_path):
        img = _image(tmp_path)
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run") as run:
            run.return_value.stdout = (
                f"eDP-1: 3840x2160, scale: 1, currently displaying: image: {img}\n"
            )
            result = HyprlandWallpaper().current()
        assert result.image_path == str(img)

    def test_falls_back_to_hyde_current_file(self, config_home, tmp_path):
        effects = config_home / "hypr" / "wallpaper_effects"
        effects.mkdir(parents=True)
        current = effects / ".wallpaper_current"
        current.write_bytes(b"\x89PNG\r\n")
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run",
                   side_effect=FileNotFoundError):
            result = HyprlandWallpaper().current()
        assert result.image_path == str(current)

    def test_falls_back_when_hyprpaper_absent(self, config_home):
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run",
                   side_effect=FileNotFoundError):
            assert HyprlandWallpaper().current() is None   # static fallback, nothing set

    def test_falls_back_when_active_path_missing_file(self, config_home):
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run") as run:
            run.return_value.stdout = "eDP-1 = /nonexistent/img.png\n"
            assert HyprlandWallpaper().current() is None

    def test_falls_back_on_timeout(self, config_home):
        with patch("infrastructure.wlroots.display.wallpaper.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("hyprctl", 2.0)):
            assert HyprlandWallpaper().current() is None


# ── SwayWallpaper ────────────────────────────────────────────────────────────

class TestSwayWallpaper:
    @pytest.fixture(autouse=True)
    def _isolate_config(self, config_home, monkeypatch):
        # Keep the host's real /etc/sway/config out of the resolver's search path.
        monkeypatch.setattr(
            SwayWallpaper, "_config_paths",
            lambda self: [config_home / "sway" / "config"],
        )

    def _write_config(self, config_home, body):
        sway_dir = config_home / "sway"
        sway_dir.mkdir()
        (sway_dir / "config").write_text(body, encoding="utf-8")

    def test_parses_output_bg(self, config_home, tmp_path):
        img = _image(tmp_path)
        self._write_config(config_home, f"output * bg {img} fill\n")
        assert SwayWallpaper().current().image_path == str(img)

    def test_expands_home_and_ignores_comments(self, config_home, tmp_path, monkeypatch):
        img = _image(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(
            config_home,
            f"# output * bg /commented/out.png fill\noutput * bg ~/{img.name} stretch\n",
        )
        assert SwayWallpaper().current().image_path == str(img)

    def test_last_bg_line_wins(self, config_home, tmp_path):
        first = _image(tmp_path, "a.png")
        second = _image(tmp_path, "b.png")
        self._write_config(
            config_home,
            f"output * bg {first} fill\noutput HDMI-1 bg {second} fill\n",
        )
        assert SwayWallpaper().current().image_path == str(second)

    def test_solid_color_bg_is_not_a_file(self, config_home):
        self._write_config(config_home, "output * bg #285577 solid_color\n")
        assert SwayWallpaper().current() is None

    def test_none_when_no_bg_line(self, config_home):
        self._write_config(config_home, "output * resolution 1920x1080\n")
        assert SwayWallpaper().current() is None

    def test_none_when_no_config(self, config_home):
        assert SwayWallpaper().current() is None


# ── WayfireWallpaper ─────────────────────────────────────────────────────────

class TestWayfireWallpaper:
    @pytest.fixture(autouse=True)
    def _isolate_session(self, config_home, tmp_path, monkeypatch):
        # Neither the host's own wf-shell defaults nor the wf-background image
        # shipped with Wayfire may leak into the resolution under test.
        monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "etc"))
        monkeypatch.setattr(
            WayfireWallpaper, "_configs",
            lambda self: [config_home / "wf-shell.ini", tmp_path / "defaults.ini"],
        )
        monkeypatch.setattr(
            "infrastructure.wlroots.display.wallpaper._WF_BACKGROUND_DEFAULT_IMAGE",
            str(tmp_path / "stock.jpg"),
        )

    def _write_config(self, config_home, body):
        (config_home / "wf-shell.ini").write_text(body, encoding="utf-8")

    def _write_pcmanfm(self, config_home, image):
        items = config_home / "pcmanfm" / "LXDE-pi-wayfire"
        items.mkdir(parents=True)
        (items / "desktop-items-0.conf").write_text(f"[*]\nwallpaper={image}\n")

    def test_reads_the_wf_background_image(self, config_home, tmp_path):
        img = _image(tmp_path)
        self._write_config(config_home, f"[background]\nimage = {img}\n")
        assert WayfireWallpaper().current().image_path == str(img)

    def test_expands_home(self, config_home, tmp_path, monkeypatch):
        img = _image(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(config_home, f"[background]\nimage = ~/{img.name}\n")
        assert WayfireWallpaper().current().image_path == str(img)

    def test_the_system_defaults_are_the_next_config(self, config_home, tmp_path):
        img = _image(tmp_path)
        self._write_config(config_home, "[panel]\nautohide = 1\n")
        (tmp_path / "defaults.ini").write_text(f"[background]\nimage = {img}\n")
        assert WayfireWallpaper().current().image_path == str(img)

    def test_an_unconfigured_session_shows_what_wf_background_shows(self, tmp_path):
        stock = _image(tmp_path, "stock.jpg")
        assert WayfireWallpaper().current().image_path == str(stock)

    def test_a_directory_resolves_to_its_first_image(self, config_home, tmp_path):
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        (gallery / "README.md").write_text("not an image")
        _image(gallery, "b.png")
        first = _image(gallery, "a.png")
        self._write_config(config_home, f"[background]\nimage = {gallery}\n")
        assert WayfireWallpaper().current().image_path == str(first)

    def test_pcmanfm_wins_over_the_stock_image(self, config_home, tmp_path):
        _image(tmp_path, "stock.jpg")
        chosen = _image(tmp_path, "rpd.jpg")
        self._write_pcmanfm(config_home, chosen)
        assert WayfireWallpaper().current().image_path == str(chosen)

    def test_falls_back_to_the_static_file(self, config_home, tmp_path):
        img = _image(tmp_path)
        (config_home / "kasual-desktop").mkdir()
        (config_home / "kasual-desktop" / "wallpaper").symlink_to(img)
        assert WayfireWallpaper().current().image_path.endswith("wallpaper")

    def test_none_when_nothing_names_a_readable_image(self, config_home):
        self._write_config(config_home, "[background]\nimage = /gone/wall.png\n")
        assert WayfireWallpaper().current() is None


class TestPcmanfmWallpaper:
    @pytest.fixture(autouse=True)
    def isolated_system_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "etc"))

    def _write_items(self, config_home, body, profile="LXDE-pi", index=0):
        items = config_home / "pcmanfm" / profile
        items.mkdir(parents=True, exist_ok=True)
        (items / f"desktop-items-{index}.conf").write_text(body, encoding="utf-8")

    def test_reads_the_wallpaper_the_desktop_shows(self, config_home, tmp_path):
        img = _image(tmp_path, "rpd.jpg")
        self._write_items(config_home, f"[*]\nwallpaper_mode=crop\nwallpaper={img}\n")
        assert PcmanfmWallpaper().current().image_path == str(img)

    def test_a_per_compositor_profile_is_found_too(self, config_home, tmp_path):
        img = _image(tmp_path, "rpd.jpg")
        self._write_items(config_home, f"[*]\nwallpaper={img}\n",
                          profile="LXDE-pi-labwc")
        assert PcmanfmWallpaper().current().image_path == str(img)

    def test_a_system_profile_is_the_next_source(self, config_home, tmp_path):
        img = _image(tmp_path, "rpd.jpg")
        system = tmp_path / "etc" / "pcmanfm" / "LXDE-pi"
        system.mkdir(parents=True)
        (system / "desktop-items-0.conf").write_text(f"[*]\nwallpaper={img}\n")
        assert PcmanfmWallpaper().current().image_path == str(img)

    def test_a_plain_colour_desktop_has_no_image(self, config_home, tmp_path):
        img = _image(tmp_path, "rpd.jpg")
        self._write_items(
            config_home, f"[*]\nwallpaper_mode=color\nwallpaper={img}\n")
        assert PcmanfmWallpaper().current() is None

    def test_a_missing_image_falls_through(self, config_home):
        self._write_items(config_home, "[*]\nwallpaper=/gone/rpd.jpg\n")
        assert PcmanfmWallpaper().current() is None

    def test_falls_back_to_the_static_file(self, config_home, tmp_path):
        img = _image(tmp_path)
        (config_home / "kasual-desktop").mkdir()
        (config_home / "kasual-desktop" / "wallpaper").symlink_to(img)
        assert PcmanfmWallpaper().current().image_path.endswith("wallpaper")

    def test_an_unparsable_config_is_skipped(self, config_home, tmp_path):
        img = _image(tmp_path, "rpd.jpg")
        self._write_items(config_home, "not an ini file at all\n", index=0)
        self._write_items(config_home, f"[*]\nwallpaper={img}\n", index=1)
        assert PcmanfmWallpaper().current().image_path == str(img)

    def test_none_without_any_pcmanfm_profile(self, config_home):
        assert PcmanfmWallpaper().current() is None

    def _write_settings(self, config_home, body, profile="lxqt"):
        profile_dir = config_home / "pcmanfm-qt" / profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "settings.conf").write_text(body, encoding="utf-8")

    def test_reads_the_wallpaper_the_lxqt_desktop_shows(self, config_home, tmp_path):
        img = _image(tmp_path, "lxqt.jpg")
        self._write_settings(
            config_home,
            f"[Desktop]\nWallpaperMode=stretch\nWallpaper={img}\n"
            "WallpaperDirectory=\n",
        )
        assert PcmanfmWallpaper().current().image_path == str(img)

    def test_a_plain_colour_lxqt_desktop_has_no_image(self, config_home, tmp_path):
        img = _image(tmp_path, "lxqt.jpg")
        self._write_settings(
            config_home, f"[Desktop]\nWallpaperMode=color\nWallpaper={img}\n")
        assert PcmanfmWallpaper().current() is None


class TestGnomeWallpaper:
    def _wallpaper(self, monkeypatch, uri):
        from infrastructure.gnome.display.wallpaper import GnomeSystemWallpaper
        wp = GnomeSystemWallpaper()

        def fake_gsettings(schema, key):
            if schema == "org.gnome.desktop.interface":
                return "default"
            return uri

        monkeypatch.setattr(wp, "_gsettings", fake_gsettings)
        return wp

    def test_direct_image_uri(self, tmp_path, monkeypatch):
        img = _image(tmp_path)
        wp = self._wallpaper(monkeypatch, f"file://{img}")
        assert wp.current().image_path == str(img)

    def test_resolves_image_from_slideshow_xml(self, tmp_path, monkeypatch):
        img = _image(tmp_path, "frame.jpg")
        xml = tmp_path / "slideshow.xml"
        xml.write_text(
            f"<background><static><file>{img}</file></static>"
            f"<transition><to>/nope/missing.jpg</to></transition></background>",
            encoding="utf-8",
        )
        wp = self._wallpaper(monkeypatch, f"file://{xml}")
        assert wp.current().image_path == str(img)

    def test_none_when_xml_has_no_usable_image(self, tmp_path, monkeypatch):
        xml = tmp_path / "empty.xml"
        xml.write_text("<background></background>", encoding="utf-8")
        wp = self._wallpaper(monkeypatch, f"file://{xml}")
        assert wp.current() is None
