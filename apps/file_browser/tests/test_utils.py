"""Tests for pure utility functions in file_browser.py."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import file_browser as fb


# ── _fmt_size ─────────────────────────────────────────────────────────────────

class TestFmtSize:
    def test_bytes(self):
        assert fb._fmt_size(0) == "0.0 B"
        assert fb._fmt_size(512) == "512.0 B"
        assert fb._fmt_size(1023) == "1023.0 B"

    def test_kilobytes(self):
        assert fb._fmt_size(1024) == "1.0 KB"
        assert fb._fmt_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert fb._fmt_size(1024 ** 2) == "1.0 MB"
        assert fb._fmt_size(int(1.5 * 1024 ** 2)) == "1.5 MB"

    def test_gigabytes(self):
        assert fb._fmt_size(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert fb._fmt_size(1024 ** 4) == "1.0 TB"


# ── _sort_entries ─────────────────────────────────────────────────────────────

def _entry(name: str, is_dir: bool, ctime: float = 0.0):
    m = MagicMock(spec=['name', 'is_dir', 'stat'])
    m.name = name
    m.is_dir.return_value = is_dir
    stat = MagicMock()
    stat.st_ctime = ctime
    m.stat.return_value = stat
    return m


class TestSortEntries:
    def _names(self, entries) -> list[str]:
        return [e.name for e in entries]

    def test_name_asc_alphabetical(self):
        entries = [_entry("z.mp4", False), _entry("a.mp4", False), _entry("m.mp4", False)]
        result = fb._sort_entries(entries, fb.SORT_NAME_ASC, folders_first=False)
        assert self._names(result) == ["a.mp4", "m.mp4", "z.mp4"]

    def test_name_desc_reverse(self):
        entries = [_entry("a.txt", False), _entry("c.txt", False), _entry("b.txt", False)]
        result = fb._sort_entries(entries, fb.SORT_NAME_DESC, folders_first=False)
        assert self._names(result) == ["c.txt", "b.txt", "a.txt"]

    def test_date_asc_oldest_first(self):
        entries = [_entry("new.txt", False, ctime=200.0), _entry("old.txt", False, ctime=100.0)]
        result = fb._sort_entries(entries, fb.SORT_DATE_ASC, folders_first=False)
        assert self._names(result) == ["old.txt", "new.txt"]

    def test_date_desc_newest_first(self):
        entries = [_entry("old.txt", False, ctime=100.0), _entry("new.txt", False, ctime=200.0)]
        result = fb._sort_entries(entries, fb.SORT_DATE_DESC, folders_first=False)
        assert self._names(result) == ["new.txt", "old.txt"]

    def test_folders_first_true(self):
        entries = [
            _entry("z_file.txt", False),
            _entry("a_dir", True),
            _entry("m_file.txt", False),
        ]
        result = fb._sort_entries(entries, fb.SORT_NAME_ASC, folders_first=True)
        names = self._names(result)
        assert names[0] == "a_dir"
        assert set(names[1:]) == {"m_file.txt", "z_file.txt"}

    def test_folders_first_false_mixed(self):
        entries = [
            _entry("z_file.txt", False),
            _entry("a_dir", True),
        ]
        result = fb._sort_entries(entries, fb.SORT_NAME_ASC, folders_first=False)
        assert self._names(result) == ["a_dir", "z_file.txt"]

    def test_empty_list(self):
        assert fb._sort_entries([], fb.SORT_NAME_ASC, folders_first=True) == []

    def test_case_insensitive_sort(self):
        entries = [_entry("Beta.txt", False), _entry("alpha.txt", False)]
        result = fb._sort_entries(entries, fb.SORT_NAME_ASC, folders_first=False)
        assert self._names(result) == ["alpha.txt", "Beta.txt"]


# ── DLNA cache ────────────────────────────────────────────────────────────────

class TestDlnaCache:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fb, '_DLNA_CACHE_FILE', tmp_path / 'dlna.json')
        monkeypatch.setattr(fb, '_CACHE_DIR', tmp_path)

        servers = [
            {"name": "Server A", "location": "http://a/", "icon_url": ""},
            {"name": "Server B", "location": "http://b/", "icon_url": "http://b/icon.png"},
        ]
        fb._save_dlna_cache(servers)
        loaded, ts = fb._load_dlna_cache()

        assert loaded == servers
        assert ts > 0

    def test_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fb, '_DLNA_CACHE_FILE', tmp_path / 'missing.json')
        loaded, ts = fb._load_dlna_cache()
        assert loaded == []
        assert ts == 0.0

    def test_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        cache_file = tmp_path / 'corrupt.json'
        cache_file.write_text("not json")
        monkeypatch.setattr(fb, '_DLNA_CACHE_FILE', cache_file)
        loaded, ts = fb._load_dlna_cache()
        assert loaded == []
        assert ts == 0.0


# ── Sort settings ─────────────────────────────────────────────────────────────

class TestSortSettings:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fb, '_SORT_SETTINGS_FILE', tmp_path / 'sort.json')
        monkeypatch.setattr(fb, '_CACHE_DIR', tmp_path)

        path_settings = {
            Path("/home/user/Videos"): (fb.SORT_DATE_DESC, True),
            Path("/home/user/Music"):  (fb.SORT_NAME_ASC,  False),
        }
        dlna_sort = (fb.SORT_DATE_ASC, False)

        fb._save_sort_settings(path_settings, dlna_sort)
        loaded_paths, loaded_dlna = fb._load_sort_settings()

        assert loaded_paths[Path("/home/user/Videos")] == (fb.SORT_DATE_DESC, True)
        assert loaded_paths[Path("/home/user/Music")]  == (fb.SORT_NAME_ASC,  False)
        assert loaded_dlna == dlna_sort

    def test_defaults_on_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fb, '_SORT_SETTINGS_FILE', tmp_path / 'missing.json')
        paths, dlna = fb._load_sort_settings()
        assert paths == {}
        assert dlna == (fb.SORT_NAME_ASC, True)

    def test_defaults_on_corrupt_file(self, tmp_path, monkeypatch):
        f = tmp_path / 'bad.json'
        f.write_text("{{{{")
        monkeypatch.setattr(fb, '_SORT_SETTINGS_FILE', f)
        paths, dlna = fb._load_sort_settings()
        assert paths == {}
        assert dlna == (fb.SORT_NAME_ASC, True)
