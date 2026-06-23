"""
Testy jednostkowe dla WindowIconResolver (desktop/window_icons.py).

Testujemy:
  - resolve_name: wyszukiwanie Name= w katalogu XDG (po nazwie pliku i StartupWMClass)
  - theme_icon_candidates: transformacje nazwy klasy okna na nazwy ikon motywu
"""

import os
import textwrap

import pytest

from infrastructure.common.qt.desktop.window_icons import WindowIconResolver, theme_icon_candidates


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

    def test_matches_by_startupwmclass(self, tmp_path, monkeypatch):
        """Plik o innej nazwie niż klasa okna, ale z pasującym StartupWMClass (przypadek Signala)."""
        _write_desktop(str(tmp_path), "signal-desktop.desktop", """\
            [Desktop Entry]
            Name=Signal
            Icon=signal-desktop
            StartupWMClass=signal
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        # desktopFileName="signal" nie pasuje do nazwy pliku signal-desktop.desktop,
        # ale StartupWMClass=signal owszem.
        assert WindowIconResolver().resolve_name("signal", "signal") == "Signal"

    def test_filename_match_takes_precedence_over_startupwmclass(self, tmp_path, monkeypatch):
        _write_desktop(str(tmp_path), "exact.desktop", """\
            [Desktop Entry]
            Name=Exact File
        """)
        _write_desktop(str(tmp_path), "other.desktop", """\
            [Desktop Entry]
            Name=Via WMClass
            StartupWMClass=exact
        """)
        monkeypatch.setattr(WindowIconResolver, '_xdg_app_dirs', staticmethod(lambda: [str(tmp_path)]))
        assert WindowIconResolver().resolve_name("exact", "exact") == "Exact File"


# ── theme_icon_candidates ───────────────────────────────────────────────────────

class TestThemeIconCandidates:
    def test_steam_app_maps_to_steam_icon(self):
        cands = theme_icon_candidates("steam_app_379430", "")
        assert cands[0] == "steam_icon_379430"

    def test_strips_jetbrains_prefix(self):
        assert "clion" in theme_icon_candidates("jetbrains-clion", "jetbrains-clion")
        assert "pycharm" in theme_icon_candidates("jetbrains-pycharm", "")

    def test_includes_raw_class(self):
        assert "brave-browser" in theme_icon_candidates("brave-browser", "")

    def test_last_dotted_segment(self):
        assert "elisa" in theme_icon_candidates("org.kde.elisa", "")

    def test_deduplicates(self):
        cands = theme_icon_candidates("signal", "signal")
        assert len(cands) == len(set(cands))

    def test_empty_inputs(self):
        assert theme_icon_candidates("", "") == []
