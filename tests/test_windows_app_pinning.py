"""Tests for WindowsAppPinning — resolving an open window to a Kasual app entry.

Mirror of the Linux ``test_app_pinning.py``: the placement mechanics (next
order, unique filename, unpin) are shared via ``AppPinningBase`` and already
covered cross-platform; here we cover the Windows-specific source resolution:

  - ``command`` comes from the window's process executable path
    (``_get_exe_path``);
  - ``name`` comes from the exe's PE version-info ``FileDescription``, falling
    back to ``resource_class.title()``, then the window title, then ``"App"``;
  - ``wm_class`` carries the window's ``resource_class`` so the pinned tile
    matches its running window back.

The filesystem side (``.desktop`` round-trip, order, unique filename, unpin) is
verified end-to-end with ``%APPDATA%`` pointed at a temp dir — the same
mechanism the Linux tests use with ``XDG_CONFIG_HOME``.

Skipped on non-Windows: ``_file_description`` uses ``ctypes.windll.version``.
"""

import configparser
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows Win32/ctypes adapters; needs ctypes.windll",
)

from domain.catalog.window import Window
from infrastructure.windows.catalog.app_pinning import WindowsAppPinning, _file_description


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """Point %APPDATA% at a temp dir; return the apps directory path.

    Mirrors the Linux ``xdg`` fixture: ``config_root()`` reads ``APPDATA`` on
    Windows, so pinning writes into ``<tmp>/kasual-desktop/apps/``."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "kasual-desktop" / "apps"


def _entry(path):
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return dict(cp["Desktop Entry"])


# ── pin — źródło App z procesu okna ────────────────────────────────────────────

class TestPinResolve:
    def test_pin_uses_exe_path_as_command(self, appdata):
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path",
                   return_value="C:\\Program Files\\App\\app.exe"), \
             patch("infrastructure.windows.catalog.app_pinning._file_description",
                   return_value="My App"):
            app = WindowsAppPinning().pin(
                Window(id="w1", title="Anything", pid=42, resource_class="app"))
        assert app is not None
        assert app.command == "C:\\Program Files\\App\\app.exe"
        assert app.name == "My App"
        assert app.wm_class == "app"

    def test_pin_writes_desktop_file_with_kasual_keys(self, appdata):
        # _join_exec shlex-quotes each token (backslash triggers quoting), so
        # the raw INI value carries single quotes; load_apps unquotes them back
        # via shlex.split. We assert on the raw INI form here.
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path",
                   return_value="C:\\App\\foo.exe"), \
             patch("infrastructure.windows.catalog.app_pinning._file_description",
                   return_value="Foo"):
            WindowsAppPinning().pin(
                Window(id="w1", title="Foo Window", pid=7, resource_class="foo"))
        files = list(appdata.glob("*.desktop"))
        assert len(files) == 1
        entry = _entry(files[0])
        assert entry["Name"] == "Foo"
        assert entry["Exec"] == "'C:\\App\\foo.exe'"   # shlex.quote'd
        assert entry["StartupWMClass"] == "foo"
        assert entry["X-Kasual-Order"] == "0"

    def test_pin_returns_none_when_exe_unresolvable(self, appdata):
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path",
                   return_value=None):
            app = WindowsAppPinning().pin(
                Window(id="w1", title="X", pid=42, resource_class="x"))
        assert app is None
        assert not appdata.exists() or not list(appdata.glob("*.desktop"))

    def test_pin_returns_none_when_pid_zero(self, appdata):
        # pid=0 means we never even try to resolve the exe.
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path") as gp:
            app = WindowsAppPinning().pin(
                Window(id="w1", title="X", pid=0, resource_class="x"))
        assert app is None
        gp.assert_not_called()


# ── pin — łańcuch fallback nazwy ───────────────────────────────────────────────

class TestPinNameFallback:
    def _pin_with(self, appdata, *, file_desc, resource_class, title):
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path",
                   return_value="C:\\App\\x.exe"), \
             patch("infrastructure.windows.catalog.app_pinning._file_description",
                   return_value=file_desc):
            return WindowsAppPinning().pin(
                Window(id="w1", title=title, pid=1, resource_class=resource_class))

    def test_file_description_wins(self, appdata):
        app = self._pin_with(appdata, file_desc="Microsoft Edge",
                             resource_class="msedge", title="Edge window")
        assert app.name == "Microsoft Edge"

    def test_falls_back_to_resource_class_titlecased(self, appdata):
        app = self._pin_with(appdata, file_desc=None,
                             resource_class="firefox", title="Some window")
        assert app.name == "Firefox"

    def test_falls_back_to_window_title_when_no_resource_class(self, appdata):
        app = self._pin_with(appdata, file_desc=None,
                             resource_class="", title="  Spaced Title  ")
        assert app.name == "Spaced Title"

    def test_falls_back_to_app_when_all_empty(self, appdata):
        app = self._pin_with(appdata, file_desc=None,
                             resource_class="", title="")
        assert app.name == "App"

    def test_wm_class_carried_from_resource_class(self, appdata):
        app = self._pin_with(appdata, file_desc="X",
                             resource_class="myapp", title="t")
        assert app.wm_class == "myapp"

    def test_wm_class_none_when_resource_class_empty(self, appdata):
        app = self._pin_with(appdata, file_desc="X",
                             resource_class="", title="t")
        assert app.wm_class is None


# ── persystencja — order, unique filename (dziedziczone z bazy) ────────────────

class TestPersistPlacement:
    def _pin(self, appdata, resource_class="foo"):
        with patch("infrastructure.windows.catalog.app_pinning._get_exe_path",
                   return_value="C:\\App\\x.exe"), \
             patch("infrastructure.windows.catalog.app_pinning._file_description",
                   return_value="X"):
            return WindowsAppPinning().pin(
                Window(id="w1", title="t", pid=1, resource_class=resource_class))

    def test_order_places_pinned_after_existing(self, appdata):
        appdata.mkdir(parents=True)
        (appdata / "a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (appdata / "b.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=1\n")
        self._pin(appdata)
        entry = _entry(appdata / "foo.desktop")
        assert entry["X-Kasual-Order"] == "2"

    def test_order_is_past_highest_even_with_gap(self, appdata):
        appdata.mkdir(parents=True)
        (appdata / "a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (appdata / "c.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=C\nExec=c\nX-Kasual-Order=2\n")
        self._pin(appdata)
        assert _entry(appdata / "foo.desktop")["X-Kasual-Order"] == "3"

    def test_unique_filename_avoids_clobbering(self, appdata):
        appdata.mkdir(parents=True)
        (appdata / "foo.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Old\nExec=old\n")
        self._pin(appdata)
        assert (appdata / "foo-2.desktop").is_file()
        assert _entry(appdata / "foo.desktop")["Name"] == "Old"   # untouched


# ── unpin (dziedziczone z bazy, ale weryfikujemy na Windows-owym adapterze) ───

class TestUnpin:
    def _seed(self, appdata):
        appdata.mkdir(parents=True)
        (appdata / "a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (appdata / "b.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=1\n")
        (appdata / "c.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=C\nExec=c\nX-Kasual-Order=2\n")

    def test_deletes_file_at_index(self, appdata):
        self._seed(appdata)
        WindowsAppPinning().unpin(1)
        remaining = sorted(p.name for p in appdata.glob("*.desktop"))
        assert remaining == ["a.desktop", "c.desktop"]

    def test_out_of_range_is_noop(self, appdata):
        self._seed(appdata)
        WindowsAppPinning().unpin(9)
        assert len(list(appdata.glob("*.desktop"))) == 3


# ── _file_description — PE version-info przez Win32 ────────────────────────────

class TestFileDescription:
    """_file_description reads the exe's PE version resource via the Win32
    version API. Mocked ctypes.windll.version exercises the parsing path."""

    def _setup(self, windll, *, size=100, get_info_ok=True,
               translation_ok=True, translation_bytes=b"\x09\x04\x04\xb0",
               desc_ok=True, desc="Microsoft Edge"):
        windll.version.GetFileVersionInfoSizeW.return_value = size
        windll.version.GetFileVersionInfoW.return_value = 1 if get_info_ok else 0
        windll.version.VerQueryValueW.return_value = 1
        # The two VerQueryValueW calls (Translation, then FileDescription)
        # share a return value; differentiate by pointer length.
        windll.version.VerQueryValueW.side_effect = (
            lambda buf, sub, ptr, length: (
                # First call: \VarFileInfo\Translation — length must be truthy.
                (1 if translation_ok else 0) if "Translation" in sub else
                # Second call: \StringFileInfo\<lang><cp>\FileDescription.
                (1 if desc_ok else 0)
            )
        )

    def test_returns_file_description(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            self._setup(windll, desc="Microsoft Edge")
            # Patch the unpack + wstring_at helpers the production code uses to
            # pull the language/codepage and the description string out of the
            # raw buffer.
            with patch("infrastructure.windows.catalog.app_pinning.struct.unpack",
                       return_value=(0x0409, 0xb004)), \
                 patch("infrastructure.windows.catalog.app_pinning.ctypes.wstring_at",
                       return_value="Microsoft Edge\x00"):
                assert _file_description("C:\\edge.exe") == "Microsoft Edge"

    def test_returns_none_when_no_version_info(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            windll.version.GetFileVersionInfoSizeW.return_value = 0
            assert _file_description("C:\\x.exe") is None

    def test_returns_none_when_get_file_version_info_fails(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            self._setup(windll, get_info_ok=False)
            assert _file_description("C:\\x.exe") is None

    def test_returns_none_when_translation_missing(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            self._setup(windll, translation_ok=False)
            assert _file_description("C:\\x.exe") is None

    def test_returns_none_when_file_description_missing(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            self._setup(windll, desc_ok=False)
            with patch("infrastructure.windows.catalog.app_pinning.struct.unpack",
                       return_value=(0x0409, 0xb004)):
                assert _file_description("C:\\x.exe") is None

    def test_strips_whitespace_and_nulls(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            windll = ctypes_mod.windll
            self._setup(windll, desc="ignored")
            with patch("infrastructure.windows.catalog.app_pinning.struct.unpack",
                       return_value=(0x0409, 0xb004)), \
                 patch("infrastructure.windows.catalog.app_pinning.ctypes.wstring_at",
                       return_value="  Spaced Name  \x00"):
                # C strings are null-terminated; the trailing \x00 is stripped,
                # then surrounding whitespace.
                assert _file_description("C:\\x.exe") == "Spaced Name"

    def test_returns_none_on_exception(self):
        with patch("infrastructure.windows.catalog.app_pinning.ctypes") as ctypes_mod:
            ctypes_mod.windll.version.GetFileVersionInfoSizeW.side_effect = OSError
            # Must not raise — the function is best-effort.
            assert _file_description("C:\\x.exe") is None
