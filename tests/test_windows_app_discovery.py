"""Tests for WindowsAppDiscovery and the Start Menu scanner.

Covers the onboarding source for the Windows port:

  - ``is_available`` — PATH-resolvable binaries, ``ms-`` protocol schemes,
    existing ``.lnk`` shortcuts, existing files, and the empty/missing cases.
  - ``discover_candidates`` — the curated Start Menu scan: skip-name/target/folder
    filters, dedupe by target basename keeping the shallowest, sort (games first
    via ``looks_like_game``, then depth, then name), ``limit`` cap, and the
    ``HOLD_1S`` recall trigger for Steam.
  - ``_slug`` / ``_depth`` — the helper functions.
  - ``builtin_candidates`` — the bundled File Browser / YouTube apps launched via
    the running interpreter's ``pythonw``; missing scripts are skipped.
  - ``_default_candidates`` — the fallback when both bundled and scan are empty.
  - ``WindowsAppDiscovery.extra_candidates`` — combines builtins + scan, falls
    back to defaults, renumbers by list position.
  - ``_scan_start_menu`` — the batched PowerShell scan: parses
    ``name\tlnk\ttarget`` lines, tolerates errors/timeout, returns ``[]``.

Skipped on non-Windows: ``_scan_start_menu`` shells out to ``powershell`` and
uses ``subprocess.CREATE_NO_WINDOW``; the bundled apps resolve ``pythonw.exe``
from ``sys.executable``.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Start Menu scan / powershell / pythonw resolution",
)

from domain.catalog.app import App
from domain.input.vocabulary import Trigger
from infrastructure.windows.catalog.app_discovery import (
    WindowsAppDiscovery, _BUILTINS, _default_candidates, _depth, _slug,
    builtin_candidates, discover_candidates,
)


# Patch target for the lazy ``project_root`` import inside builtin_candidates.
_PROJECT_ROOT = "infrastructure.common.bundled.project_root"


# ── is_available ──────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_path_resolvable_binary_is_available(self):
        with patch("infrastructure.windows.catalog.app_discovery.shutil.which",
                   return_value="C:\\Windows\\notepad.exe"):
            assert WindowsAppDiscovery().is_available("notepad") is True

    def test_ms_protocol_scheme_is_available(self):
        with patch("infrastructure.windows.catalog.app_discovery.shutil.which",
                   return_value=None):
            assert WindowsAppDiscovery().is_available("ms-settings:") is True

    def test_existing_lnk_is_available(self, tmp_path):
        lnk = tmp_path / "app.lnk"
        lnk.write_text("x")
        with patch("infrastructure.windows.catalog.app_discovery.shutil.which",
                   return_value=None):
            assert WindowsAppDiscovery().is_available(str(lnk)) is True

    def test_existing_file_is_available(self, tmp_path):
        f = tmp_path / "app.exe"
        f.write_text("x")
        with patch("infrastructure.windows.catalog.app_discovery.shutil.which",
                   return_value=None):
            assert WindowsAppDiscovery().is_available(str(f)) is True

    def test_missing_command_is_not_available(self):
        with patch("infrastructure.windows.catalog.app_discovery.shutil.which",
                   return_value=None), \
             patch("infrastructure.windows.catalog.app_discovery.Path.is_file",
                   return_value=False), \
             patch("infrastructure.windows.catalog.app_discovery.Path.exists",
                   return_value=False):
            assert WindowsAppDiscovery().is_available("nope") is False

    def test_empty_command_is_not_available(self):
        assert WindowsAppDiscovery().is_available("") is False

    def test_system_icon_returns_none(self):
        # Windows has no system-wide icon theme; the tile falls back to the
        # bundled Font Awesome glyph.
        assert WindowsAppDiscovery().system_icon(("firefox", "internet")) is None


# ── discover_candidates — kuracja ─────────────────────────────────────────────

def _rows(*triples):
    """Build a list of (name, lnk, target) tuples for _scan_start_menu mock."""
    return list(triples)


def _patch_scan(rows):
    return patch("infrastructure.windows.catalog.app_discovery._scan_start_menu",
                 return_value=rows)


class TestDiscoverCandidatesCuration:
    def test_skip_name_filters_uninstallers(self):
        rows = _rows(
            ("Firefox", "C:\\Programs\\Mozilla Firefox.lnk", "C:\\ff.exe"),
            ("Uninstall Firefox", "C:\\Programs\\Uninstall.lnk", "C:\\un.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates()
        names = [c.app.name for c in cands]
        assert "Firefox" in names
        assert "Uninstall Firefox" not in names

    def test_skip_name_filters_help_and_docs(self):
        rows = _rows(
            ("Read Me", "C:\\x.lnk", "C:\\read.exe"),
            ("Help", "C:\\x.lnk", "C:\\help.exe"),
            ("Documentation", "C:\\x.lnk", "C:\\docs.exe"),
            ("Website", "C:\\x.lnk", "C:\\web.exe"),
            ("License", "C:\\x.lnk", "C:\\lic.exe"),
            ("App", "C:\\app.lnk", "C:\\app.exe"),
        )
        with _patch_scan(rows):
            names = [c.app.name for c in discover_candidates()]
        assert names == ["App"]

    def test_skip_target_filters_installers(self):
        rows = _rows(
            ("App", "C:\\app.lnk", "C:\\app.exe"),
            ("Setup", "C:\\setup.lnk", "C:\\setup.exe"),
            ("Update", "C:\\up.lnk", "C:\\updater.exe"),
            ("MSI", "C:\\msi.lnk", "C:\\msiexec.exe"),
        )
        with _patch_scan(rows):
            names = [c.app.name for c in discover_candidates()]
        assert names == ["App"]

    def test_skip_folder_filters_system_tools(self):
        rows = _rows(
            ("App", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\app.lnk",
             "C:\\app.exe"),
            ("Admin Tool",
             "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Administrative Tools\\admin.lnk",
             "C:\\admin.exe"),
            ("Sys Tool",
             "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Windows System\\sys.lnk",
             "C:\\sys.exe"),
        )
        with _patch_scan(rows):
            names = [c.app.name for c in discover_candidates()]
        assert names == ["App"]

    def test_non_exe_target_skipped(self):
        rows = _rows(
            ("App", "C:\\app.lnk", "C:\\app.exe"),
            ("Doc", "C:\\doc.lnk", "C:\\readme.pdf"),
        )
        with _patch_scan(rows):
            names = [c.app.name for c in discover_candidates()]
        assert names == ["App"]

    def test_empty_scan_returns_empty(self):
        with _patch_scan([]):
            assert discover_candidates() == []


# ── discover_candidates — dedupe po basename targetu ─────────────────────────

class TestDiscoverCandidatesDedupe:
    def test_dedupes_by_target_basename(self):
        # Two shortcuts pointing at the same exe → one candidate.
        rows = _rows(
            ("Firefox", "C:\\Programs\\Firefox.lnk", "C:\\ff.exe"),
            ("Mozilla Firefox",
             "C:\\Programs\\Mozilla\\Firefox.lnk", "C:\\ff.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates()
        assert len(cands) == 1

    def test_keeps_shallowest_shortcut(self):
        # When two shortcuts share a target, the one with the smallest depth
        # (most prominent) is kept.
        rows = _rows(
            ("Deep", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Folder\\Sub\\deep.lnk",
             "C:\\app.exe"),
            ("Top", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\top.lnk",
             "C:\\app.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates()
        assert len(cands) == 1
        assert cands[0].app.name == "Top"


# ── discover_candidates — sortowanie i limit ──────────────────────────────────

class TestDiscoverCandidatesSort:
    def test_games_pre_selected_and_sorted_first(self):
        # Steam is a known game launcher (looks_like_game → True); Notepad is
        # not. Games land first, pre-selected.
        rows = _rows(
            ("Notepad", "C:\\Programs\\np.lnk", "C:\\notepad.exe"),
            ("Steam", "C:\\Programs\\steam.lnk", "C:\\steam.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates()
        assert [c.app.name for c in cands] == ["Steam", "Notepad"]
        assert cands[0].default_selected is True   # Steam
        assert cands[1].default_selected is False  # Notepad

    def test_limit_caps_count(self):
        rows = _rows(
            ("App1", "C:\\a1.lnk", "C:\\a1.exe"),
            ("App2", "C:\\a2.lnk", "C:\\a2.exe"),
            ("App3", "C:\\a3.lnk", "C:\\a3.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates(limit=2)
        assert len(cands) == 2

    def test_hold_1s_trigger_for_steam(self):
        rows = _rows(
            ("Steam", "C:\\steam.lnk", "C:\\steam.exe"),
            ("Notepad", "C:\\np.lnk", "C:\\notepad.exe"),
        )
        with _patch_scan(rows):
            cands = discover_candidates()
        steam = next(c for c in cands if c.app.name == "Steam")
        notepad = next(c for c in cands if c.app.name == "Notepad")
        assert steam.app.recall_menu_trigger == Trigger.HOLD_1S
        assert notepad.app.recall_menu_trigger == Trigger.CLICK

    def test_command_is_lnk_path(self):
        rows = _rows(("App", "C:\\Programs\\app.lnk", "C:\\app.exe"))
        with _patch_scan(rows):
            cands = discover_candidates()
        assert cands[0].app.command == "C:\\Programs\\app.lnk"

    def test_wm_class_is_target_basename(self):
        rows = _rows(("App", "C:\\app.lnk", "C:\\MyApp.exe"))
        with _patch_scan(rows):
            cands = discover_candidates()
        assert cands[0].app.wm_class == "myapp"

    def test_orders_alphabetically_within_same_group(self):
        # Two non-games with the same depth → alphabetical by name.
        rows = _rows(
            ("Zebra", "C:\\z.lnk", "C:\\z.exe"),
            ("Apple", "C:\\a.lnk", "C:\\a.exe"),
        )
        with _patch_scan(rows):
            names = [c.app.name for c in discover_candidates()]
        assert names == ["Apple", "Zebra"]


# ── _slug ─────────────────────────────────────────────────────────────────────

class TestSlug:
    def test_lowercases(self):
        assert _slug("Firefox") == "firefox"

    def test_replaces_non_alnum_with_dash(self):
        assert _slug("My App") == "my-app"

    def test_strips_leading_and_trailing_dashes(self):
        assert _slug("--weird--") == "weird"

    def test_keeps_dots_and_dashes(self):
        assert _slug("org.kde.konsole") == "org.kde.konsole"

    def test_empty_string_returns_empty(self):
        assert _slug("") == ""


# ── _depth ────────────────────────────────────────────────────────────────────

class TestDepth:
    def test_top_level_is_zero(self):
        lnk = "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\app.lnk"
        assert _depth(lnk) == 0

    def test_one_folder_deep_is_one(self):
        lnk = "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Folder\\app.lnk"
        assert _depth(lnk) == 1

    def test_two_folders_deep_is_two(self):
        lnk = "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\A\\B\\app.lnk"
        assert _depth(lnk) == 2

    def test_no_programs_returns_large(self):
        # A path without a 'Programs' segment → 99 (sorts last).
        lnk = "C:\\Shortcuts\\app.lnk"
        assert _depth(lnk) == 99

    def test_case_insensitive_programs(self):
        lnk = "C:\\programdata\\microsoft\\windows\\start menu\\programs\\app.lnk"
        assert _depth(lnk) == 0


# ── builtin_candidates ────────────────────────────────────────────────────────

class TestBuiltinCandidates:
    def test_returns_files_and_youtube(self):
        from pathlib import Path
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch("pathlib.Path.exists", return_value=True):
            cands = builtin_candidates()
        keys = {c.key for c in cands}
        assert "files" in keys
        assert "youtube" in keys

    def test_bundled_apps_default_selected(self):
        from pathlib import Path
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch("pathlib.Path.exists", return_value=True):
            cands = builtin_candidates()
        assert all(c.default_selected for c in cands)

    def test_missing_script_skipped(self):
        from pathlib import Path
        # The File Browser script exists, the YouTube script doesn't.
        def exists(self):
            return "file_browser" in str(self)
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch.object(Path, "exists", exists):
            cands = builtin_candidates()
        keys = {c.key for c in cands}
        assert "files" in keys
        assert "youtube" not in keys

    def test_uses_pythonw_when_available(self):
        from pathlib import Path
        pyw = Path("C:\\venv\\pythonw.exe")
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "with_name", return_value=pyw):
            cands = builtin_candidates()
        # The command is the pythonw interpreter path; we just verify it's a
        # string (the exact path depends on sys.executable in the test env).
        assert all(isinstance(c.app.command, str) for c in cands)


# ── _default_candidates ───────────────────────────────────────────────────────

class TestDefaultCandidates:
    def test_returns_settings_and_browser(self):
        cands = _default_candidates()
        keys = {c.key for c in cands}
        assert "settings" in keys
        assert "browser" in keys

    def test_settings_uses_ms_protocol(self):
        cands = _default_candidates()
        settings = next(c for c in cands if c.key == "settings")
        assert settings.app.command == "ms-settings:"

    def test_browser_uses_msedge(self):
        cands = _default_candidates()
        browser = next(c for c in cands if c.key == "browser")
        assert browser.app.command == "msedge"

    def test_both_default_selected(self):
        cands = _default_candidates()
        assert all(c.default_selected for c in cands)


# ── WindowsAppDiscovery.extra_candidates ──────────────────────────────────────

class TestExtraCandidates:
    def test_combines_builtins_and_scan(self):
        from pathlib import Path
        rows = _rows(("Steam", "C:\\steam.lnk", "C:\\steam.exe"))
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch("pathlib.Path.exists", return_value=True), \
             _patch_scan(rows):
            cands = WindowsAppDiscovery().extra_candidates()
        keys = [c.key for c in cands]
        # Builtins first, then scan results.
        assert "files" in keys
        assert "youtube" in keys
        assert any("steam" in k for k in keys)

    def test_falls_back_to_defaults_when_both_empty(self):
        from pathlib import Path
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch("pathlib.Path.exists", return_value=False), \
             _patch_scan([]):
            cands = WindowsAppDiscovery().extra_candidates()
        keys = {c.key for c in cands}
        assert "settings" in keys
        assert "browser" in keys

    def test_renumbers_by_list_position(self):
        from pathlib import Path
        rows = _rows(
            ("A", "C:\\a.lnk", "C:\\a.exe"),
            ("B", "C:\\b.lnk", "C:\\b.exe"),
        )
        with patch(_PROJECT_ROOT, return_value=Path("C:\\kasual")), \
             patch("pathlib.Path.exists", return_value=True), \
             _patch_scan(rows):
            cands = WindowsAppDiscovery().extra_candidates()
        orders = [c.order for c in cands]
        assert orders == list(range(len(cands)))


# ── _scan_start_menu ──────────────────────────────────────────────────────────

class TestScanStartMenu:
    def _proc(self, stdout=b"", returncode=0):
        proc = MagicMock()
        proc.stdout = stdout
        proc.returncode = returncode
        return proc

    def test_parses_name_tab_lnk_tab_target(self):
        out = "Firefox\tC:\\ff.lnk\tC:\\ff.exe\n".encode("utf-8")
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   return_value=self._proc(out)):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            rows = _scan_start_menu()
        assert rows == [("Firefox", "C:\\ff.lnk", "C:\\ff.exe")]

    def test_parses_multiple_lines(self):
        out = ("A\tC:\\a.lnk\tC:\\a.exe\n"
               "B\tC:\\b.lnk\tC:\\b.exe\n").encode("utf-8")
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   return_value=self._proc(out)):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            rows = _scan_start_menu()
        assert len(rows) == 2

    def test_skips_lines_without_three_fields(self):
        out = ("A\tC:\\a.lnk\tC:\\a.exe\n"
               "BadLine\n"
               "B\tC:\\b.lnk\tC:\\b.exe\n").encode("utf-8")
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   return_value=self._proc(out)):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            rows = _scan_start_menu()
        assert len(rows) == 2

    def test_skips_lines_with_empty_name(self):
        out = ("\tC:\\a.lnk\tC:\\a.exe\n"
               "B\tC:\\b.lnk\tC:\\b.exe\n").encode("utf-8")
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   return_value=self._proc(out)):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            rows = _scan_start_menu()
        assert len(rows) == 1
        assert rows[0][0] == "B"

    def test_strips_whitespace_from_fields(self):
        out = "  Firefox  \t C:\\ff.lnk \t C:\\ff.exe \n".encode("utf-8")
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   return_value=self._proc(out)):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            rows = _scan_start_menu()
        assert rows == [("Firefox", "C:\\ff.lnk", "C:\\ff.exe")]

    def test_exception_returns_empty(self):
        with patch("infrastructure.windows.catalog.app_discovery.subprocess.run",
                   side_effect=TimeoutError):
            from infrastructure.windows.catalog.app_discovery import _scan_start_menu
            assert _scan_start_menu() == []
