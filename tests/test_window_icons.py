"""
Testy jednostkowe dla WindowIconResolver (desktop/window_icons.py).

Testujemy:
  - resolve_name: wyszukiwanie Name= w katalogu XDG
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
