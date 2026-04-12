"""
Testy jednostkowe dla helperów ikon i nazw okien KWin (desktop/window_icons.py).

Testujemy:
  - _icon_name_from_desktop: parsowanie pola Icon= z pliku .desktop
  - resolve_window_name:     wyszukiwanie Name= w katalogu XDG
"""

import os
import textwrap

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_caches():
    """Czyści lru_cache przed każdym testem, by wyniki nie przeciekały."""
    from desktop.window_icons import resolve_window_name, resolve_window_icon
    resolve_window_name.cache_clear()
    resolve_window_icon.cache_clear()
    yield
    resolve_window_name.cache_clear()
    resolve_window_icon.cache_clear()


def _write_desktop(dir_path: str, filename: str, content: str) -> str:
    path = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    return path


# ── _icon_name_from_desktop ───────────────────────────────────────────────────

class TestIconNameFromDesktop:
    def test_returns_icon_value(self, tmp_path):
        from desktop.window_icons import _icon_name_from_desktop
        p = _write_desktop(str(tmp_path), "app.desktop", """\
            [Desktop Entry]
            Name=MyApp
            Icon=myapp-icon
        """)
        assert _icon_name_from_desktop(p) == "myapp-icon"

    def test_returns_absolute_path_icon(self, tmp_path):
        from desktop.window_icons import _icon_name_from_desktop
        p = _write_desktop(str(tmp_path), "snap.desktop", """\
            [Desktop Entry]
            Name=SnapApp
            Icon=/snap/myapp/current/icon.png
        """)
        assert _icon_name_from_desktop(p) == "/snap/myapp/current/icon.png"

    def test_returns_none_when_no_icon_key(self, tmp_path):
        from desktop.window_icons import _icon_name_from_desktop
        p = _write_desktop(str(tmp_path), "noicon.desktop", """\
            [Desktop Entry]
            Name=NoIcon
        """)
        assert _icon_name_from_desktop(p) is None

    def test_returns_none_for_nonexistent_file(self):
        from desktop.window_icons import _icon_name_from_desktop
        assert _icon_name_from_desktop("/nonexistent/path/app.desktop") is None

    def test_returns_none_for_empty_file(self, tmp_path):
        from desktop.window_icons import _icon_name_from_desktop
        p = str(tmp_path / "empty.desktop")
        open(p, "w").close()
        assert _icon_name_from_desktop(p) is None


# ── resolve_window_name ───────────────────────────────────────────────────────

class TestResolveWindowName:
    def test_finds_name_by_desktop_file(self, tmp_path):
        from desktop.window_icons import resolve_window_name
        _write_desktop(str(tmp_path), "myapp.desktop", """\
            [Desktop Entry]
            Name=My Application
            Icon=myapp
        """)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("myapp", "myapp")
        assert result == "My Application"

    def test_appends_desktop_extension_if_missing(self, tmp_path):
        from desktop.window_icons import resolve_window_name
        _write_desktop(str(tmp_path), "coolapp.desktop", """\
            [Desktop Entry]
            Name=Cool App
        """)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("coolapp", "")
        assert result == "Cool App"

    def test_does_not_double_append_extension(self, tmp_path):
        from desktop.window_icons import resolve_window_name
        _write_desktop(str(tmp_path), "already.desktop", """\
            [Desktop Entry]
            Name=Already Extended
        """)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("already.desktop", "")
        assert result == "Already Extended"

    def test_falls_back_to_resource_class(self, tmp_path):
        from desktop.window_icons import resolve_window_name
        _write_desktop(str(tmp_path), "resourceclass.desktop", """\
            [Desktop Entry]
            Name=From ResourceClass
        """)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("", "resourceclass")
        assert result == "From ResourceClass"

    def test_returns_none_when_not_found(self, tmp_path):
        from desktop.window_icons import resolve_window_name
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("doesnotexist", "alsomissing")
        assert result is None

    def test_skips_duplicate_candidate_when_desktop_file_equals_resource_class(self, tmp_path):
        """Gdy desktop_file == resource_class, kandydat powinien być dodany tylko raz."""
        from desktop.window_icons import resolve_window_name
        _write_desktop(str(tmp_path), "same.desktop", """\
            [Desktop Entry]
            Name=Same Name
        """)
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("desktop.window_icons._xdg_app_dirs", lambda: [str(tmp_path)])
            result = resolve_window_name("same", "same")
        assert result == "Same Name"
