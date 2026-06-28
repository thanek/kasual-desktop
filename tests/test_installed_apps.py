"""Tests for the Linux installed-app scanner (XdgInstalledApps).

Pure file scanning against a temp XDG tree — the freedesktop→App rules it relies
on are the domain's (covered by test_domain_app); here we check the directory
walk, the skip rules and the user-overrides-system precedence.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux scanner")

from infrastructure.linux.catalog.installed_apps import XdgInstalledApps


def _write(path, **keys) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "[Desktop Entry]\n" + "".join(f"{k}={v}\n" for k, v in keys.items())
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    """An isolated set of application dirs: a user dir and one system dir.

    Patches the scanner's ``_xdg_app_dirs`` directly — env vars alone don't
    isolate it, since the dir list also includes hard-coded flatpak export paths
    that exist on the host."""
    user_apps = tmp_path / "home" / "applications"
    system_apps = tmp_path / "system" / "applications"
    monkeypatch.setattr(
        "infrastructure.linux.catalog.installed_apps._xdg_app_dirs",
        lambda: [str(user_apps), str(system_apps)],
    )
    return user_apps, system_apps


class TestScan:
    def test_lists_application_entries_sorted_by_name(self, xdg):
        user_apps, _ = xdg
        _write(user_apps / "zed.desktop", Type="Application", Name="Zed", Exec="zed")
        _write(user_apps / "alpha.desktop", Type="Application", Name="Alpha", Exec="alpha")
        names = [c.app.name for c in XdgInstalledApps().scan()]
        assert names == ["Alpha", "Zed"]

    def test_skips_nodisplay_and_hidden(self, xdg):
        user_apps, _ = xdg
        _write(user_apps / "ok.desktop", Type="Application", Name="Ok", Exec="ok")
        _write(user_apps / "hidden.desktop", Type="Application", Name="H", Exec="h",
               NoDisplay="true")
        _write(user_apps / "gone.desktop", Type="Application", Name="G", Exec="g",
               Hidden="true")
        keys = {c.key for c in XdgInstalledApps().scan()}
        assert keys == {"ok"}

    def test_skips_malformed_entry(self, xdg):
        user_apps, _ = xdg
        _write(user_apps / "good.desktop", Type="Application", Name="Good", Exec="good")
        _write(user_apps / "bad.desktop", Type="Application", Name="")   # no Exec/Name
        keys = {c.key for c in XdgInstalledApps().scan()}
        assert keys == {"good"}

    def test_user_dir_overrides_system_for_same_filename(self, xdg):
        user_apps, system_apps = xdg
        _write(system_apps / "editor.desktop", Type="Application",
               Name="System Editor", Exec="sysedit")
        _write(user_apps / "editor.desktop", Type="Application",
               Name="My Editor", Exec="myedit")
        cands = XdgInstalledApps().scan()
        editor = [c for c in cands if c.key == "editor"]
        assert len(editor) == 1
        assert editor[0].app.name == "My Editor"

    def test_honors_only_show_in_for_current_desktop(self, xdg, monkeypatch):
        user_apps, _ = xdg
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
        _write(user_apps / "kde-app.desktop", Type="Application", Name="KdeApp",
               Exec="kapp", OnlyShowIn="KDE;")
        _write(user_apps / "gnome-only.desktop", Type="Application", Name="GnomeOnly",
               Exec="gapp", OnlyShowIn="GNOME;")
        keys = {c.key for c in XdgInstalledApps().scan()}
        assert keys == {"kde-app"}

    def test_honors_not_show_in_for_current_desktop(self, xdg, monkeypatch):
        user_apps, _ = xdg
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
        _write(user_apps / "shown.desktop", Type="Application", Name="Shown", Exec="s")
        _write(user_apps / "not-kde.desktop", Type="Application", Name="NotKde",
               Exec="n", NotShowIn="KDE;")
        keys = {c.key for c in XdgInstalledApps().scan()}
        assert keys == {"shown"}

    def test_candidates_are_never_preselected(self, xdg):
        user_apps, _ = xdg
        _write(user_apps / "a.desktop", Type="Application", Name="A", Exec="a")
        assert all(not c.default_selected for c in XdgInstalledApps().scan())

    def test_missing_dirs_yield_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "infrastructure.linux.catalog.installed_apps._xdg_app_dirs",
            lambda: [str(tmp_path / "nope"), str(tmp_path / "also-nope")],
        )
        assert XdgInstalledApps().scan() == []
