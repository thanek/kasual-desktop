"""
Testy jednostkowe dla WindowIconResolver (desktop/window_icons.py).

Testujemy:
  - _icon_name_from_desktop: parsowanie pola Icon= z pliku .desktop
  - resolve_name:            wyszukiwanie Name= w katalogu XDG
"""

import os
import textwrap

import pytest

from desktop.window_icons import WindowIconResolver


def _write_desktop(dir_path: str, filename: str, content: str) -> str:
    path = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    return path


# ── _icon_name_from_desktop ───────────────────────────────────────────────────

class TestIconNameFromDesktop:
    def test_returns_icon_value(self, tmp_path):
        p = _write_desktop(str(tmp_path), "app.desktop", """\
            [Desktop Entry]
            Name=MyApp
            Icon=myapp-icon
        """)
        assert WindowIconResolver._icon_name_from_desktop(p) == "myapp-icon"

    def test_returns_absolute_path_icon(self, tmp_path):
        p = _write_desktop(str(tmp_path), "snap.desktop", """\
            [Desktop Entry]
            Name=SnapApp
            Icon=/snap/myapp/current/icon.png
        """)
        assert WindowIconResolver._icon_name_from_desktop(p) == "/snap/myapp/current/icon.png"

    def test_returns_none_when_no_icon_key(self, tmp_path):
        p = _write_desktop(str(tmp_path), "noicon.desktop", """\
            [Desktop Entry]
            Name=NoIcon
        """)
        assert WindowIconResolver._icon_name_from_desktop(p) is None

    def test_returns_none_for_nonexistent_file(self):
        assert WindowIconResolver._icon_name_from_desktop("/nonexistent/path/app.desktop") is None

    def test_returns_none_for_empty_file(self, tmp_path):
        p = str(tmp_path / "empty.desktop")
        open(p, "w").close()
        assert WindowIconResolver._icon_name_from_desktop(p) is None


# ── resolve_name ──────────────────────────────────────────────────────────────

class TestResolveWindowName:
    def test_finds_name_by_desktop_file(self, tmp_path, monkeypatch):
        _write_desktop(str(tmp_path), "myapp.desktop", """\
            [Desktop Entry]
            Name=My Application
            Icon=myapp
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("myapp", "myapp") == "My Application"

    def test_appends_desktop_extension_if_missing(self, tmp_path, monkeypatch):
        _write_desktop(str(tmp_path), "coolapp.desktop", """\
            [Desktop Entry]
            Name=Cool App
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("coolapp", "") == "Cool App"

    def test_does_not_double_append_extension(self, tmp_path, monkeypatch):
        _write_desktop(str(tmp_path), "already.desktop", """\
            [Desktop Entry]
            Name=Already Extended
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("already.desktop", "") == "Already Extended"

    def test_falls_back_to_resource_class(self, tmp_path, monkeypatch):
        _write_desktop(str(tmp_path), "resourceclass.desktop", """\
            [Desktop Entry]
            Name=From ResourceClass
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("", "resourceclass") == "From ResourceClass"

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("doesnotexist", "alsomissing") is None

    def test_skips_duplicate_candidate_when_desktop_file_equals_resource_class(self, tmp_path, monkeypatch):
        """Gdy desktop_file == resource_class, kandydat powinien być dodany tylko raz."""
        _write_desktop(str(tmp_path), "same.desktop", """\
            [Desktop Entry]
            Name=Same Name
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("same", "same") == "Same Name"
