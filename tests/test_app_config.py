"""Tests for the .desktop app loader (system.app_config)."""

import pytest

from system.app_config import load_apps, _parse_exec, _parse_env


def _write(directory, filename, content):
    (directory / filename).write_text(content, encoding="utf-8")


@pytest.fixture
def apps_root(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME at a temp dir and return the apps directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = tmp_path / "kasual-desktop" / "apps"
    d.mkdir(parents=True)
    return d


# ── Exec parsing ────────────────────────────────────────────────────────────

class TestExecParsing:
    def test_command_and_args(self):
        assert _parse_exec("steam steam://open/bigpicture") == (
            "steam", ["steam://open/bigpicture"]
        )

    def test_field_codes_stripped(self):
        assert _parse_exec("firefox --kiosk %U") == ("firefox", ["--kiosk"])

    def test_quoted_args(self):
        assert _parse_exec('app "a b" c') == ("app", ["a b", "c"])

    def test_escaped_percent(self):
        assert _parse_exec("app 50%%") == ("app", ["50%"])

    def test_empty(self):
        assert _parse_exec("   ") == (None, [])


# ── Env parsing ───────────────────────────────────────────────────────────────

class TestEnvParsing:
    def test_basic(self):
        assert _parse_env("A=1;B=2") == {"A": "1", "B": "2"}

    def test_none_and_empty(self):
        assert _parse_env(None) == {}
        assert _parse_env("") == {}

    def test_ignores_malformed(self):
        assert _parse_env("A=1;garbage;B=2") == {"A": "1", "B": "2"}

    def test_value_keeps_equals(self):
        assert _parse_env("URL=http://x?a=b") == {"URL": "http://x?a=b"}


# ── load_apps ─────────────────────────────────────────────────────────────────

class TestLoadApps:
    def test_maps_all_fields(self, apps_root):
        _write(apps_root, "steam.desktop", (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Steam\n"
            "Exec=steam steam://open/bigpicture\n"
            "X-Kasual-Icon=fa5b.steam\n"
            "X-Kasual-Color=#1b2838\n"
            "X-Kasual-RecallMenuTrigger=BTN_MODE_HOLD_1S\n"
            "X-Kasual-HideGraceMs=500\n"
            "X-Kasual-Env=MANGOHUD=1\n"
            "X-Kasual-Order=10\n"
        ))
        apps = load_apps()
        assert len(apps) == 1
        a = apps[0]
        assert a.name == "Steam"
        assert a.command == "steam"
        assert a.args == ("steam://open/bigpicture",)
        assert a.icon == "fa5b.steam"
        assert a.icon_theme is None
        assert a.color == "#1b2838"
        assert a.recall_menu_trigger == "BTN_MODE_HOLD_1S"
        assert a.launch_hide_grace_ms == 500
        assert a.env == {"MANGOHUD": "1"}

    def test_defaults(self, apps_root):
        _write(apps_root, "min.desktop",
               "[Desktop Entry]\nType=Application\nName=Min\nExec=min\n")
        a = load_apps()[0]
        assert a.icon is None
        assert a.icon_theme is None
        assert a.color == "#2e3440"
        assert a.recall_menu_trigger == "BTN_MODE_CLICK"
        assert a.launch_hide_grace_ms == 0
        assert a.env == {}

    def test_icon_theme_used_without_kasual_icon(self, apps_root):
        _write(apps_root, "themed.desktop",
               "[Desktop Entry]\nType=Application\nName=T\nExec=t\nIcon=org.kde.themed\n")
        a = load_apps()[0]
        assert a.icon is None
        assert a.icon_theme == "org.kde.themed"

    def test_order_then_filename(self, apps_root):
        _write(apps_root, "b.desktop",
               "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=20\n")
        _write(apps_root, "a.desktop",
               "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=10\n")
        _write(apps_root, "z.desktop",
               "[Desktop Entry]\nType=Application\nName=Z\nExec=z\n")
        _write(apps_root, "m.desktop",
               "[Desktop Entry]\nType=Application\nName=M\nExec=m\n")
        # Explicit X-Kasual-Order first (A, B); then unordered by filename (m, z).
        assert [a.name for a in load_apps()] == ["A", "B", "M", "Z"]

    def test_skips_nodisplay_hidden_and_non_application(self, apps_root):
        _write(apps_root, "nodisplay.desktop",
               "[Desktop Entry]\nType=Application\nName=N\nExec=n\nNoDisplay=true\n")
        _write(apps_root, "hidden.desktop",
               "[Desktop Entry]\nType=Application\nName=H\nExec=h\nHidden=true\n")
        _write(apps_root, "link.desktop",
               "[Desktop Entry]\nType=Link\nName=L\nURL=http://x\n")
        _write(apps_root, "ok.desktop",
               "[Desktop Entry]\nType=Application\nName=OK\nExec=ok\n")
        assert [a.name for a in load_apps()] == ["OK"]

    def test_skips_missing_name_or_exec(self, apps_root):
        _write(apps_root, "noexec.desktop",
               "[Desktop Entry]\nType=Application\nName=X\n")
        _write(apps_root, "noname.desktop",
               "[Desktop Entry]\nType=Application\nExec=x\n")
        assert load_apps() == []

    def test_bad_file_is_skipped(self, apps_root):
        _write(apps_root, "junk.desktop", "this is not a desktop file at all")
        _write(apps_root, "ok.desktop",
               "[Desktop Entry]\nType=Application\nName=OK\nExec=ok\n")
        assert [a.name for a in load_apps()] == ["OK"]

    def test_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "does-not-exist"))
        assert load_apps() == []
