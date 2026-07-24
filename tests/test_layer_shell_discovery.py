"""Tests for how LayerShellQt is found.

The soname is no evidence of which Qt a build belongs to — the 5.27 series installs
``libLayerShellQtInterface.so.5`` even when built against Qt 6 — so the deciding
signal is the shell-integration plugin sitting inside *this* Qt's plugin directory.
Getting that wrong is expensive: a Qt without the plugin leaves every window
unmapped once the integration is named anyway.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from infrastructure.linux.wayland import layer_shell


@pytest.fixture
def plugin_dirs(tmp_path, monkeypatch):
    """A fake Qt plugin root and a fake QT_PLUGIN_PATH root, neither populated."""
    qt_root, extra_root = tmp_path / "qt", tmp_path / "extra"
    monkeypatch.delenv("QT_PLUGIN_PATH", raising=False)
    monkeypatch.setattr(layer_shell.QLibraryInfo, "path",
                        staticmethod(lambda _p: str(qt_root)))
    return qt_root, extra_root


def _install(root: Path) -> Path:
    plugin = root / "wayland-shell-integration" / "liblayer-shell.so"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_bytes(b"")
    return plugin


class TestIntegrationPlugin:
    def test_found_in_this_qt_plugin_directory(self, plugin_dirs):
        qt_root, _ = plugin_dirs
        plugin = _install(qt_root)
        assert layer_shell.integration_plugin() == str(plugin)

    def test_absent_when_this_qt_ships_none(self, plugin_dirs):
        # A pip-installed PyQt6 — a newer Qt bundling its own plugins — answers
        # here with its own directory, which has no layer-shell integration.
        assert layer_shell.integration_plugin() is None

    def test_found_through_qt_plugin_path(self, plugin_dirs, monkeypatch):
        _, extra_root = plugin_dirs
        plugin = _install(extra_root)
        monkeypatch.setenv("QT_PLUGIN_PATH", str(extra_root))
        assert layer_shell.integration_plugin() == str(plugin)

    def test_qt_plugin_path_is_searched_before_this_qt(self, plugin_dirs, monkeypatch):
        qt_root, extra_root = plugin_dirs
        _install(qt_root)
        override = _install(extra_root)
        monkeypatch.setenv("QT_PLUGIN_PATH", str(extra_root))
        assert layer_shell.integration_plugin() == str(override)

    def test_empty_entries_in_qt_plugin_path_are_skipped(self, plugin_dirs, monkeypatch):
        qt_root, _ = plugin_dirs
        plugin = _install(qt_root)
        monkeypatch.setenv("QT_PLUGIN_PATH", "::")
        assert layer_shell.integration_plugin() == str(plugin)


class TestAvailability:
    @pytest.fixture(autouse=True)
    def _forget_cached_result(self):
        before = layer_shell._lib
        layer_shell._lib = None
        yield
        layer_shell._lib = before

    def test_without_the_plugin_the_library_is_never_opened(self, plugin_dirs):
        with patch.object(layer_shell.ctypes, "CDLL") as cdll:
            assert layer_shell.is_available() is False
        # Opening it regardless could pull a Qt5 build into this Qt6 process.
        cdll.assert_not_called()

    def test_tries_every_known_soname(self, plugin_dirs):
        _install(plugin_dirs[0])
        with patch.object(layer_shell.ctypes, "CDLL",
                          side_effect=OSError("nope")) as cdll:
            assert layer_shell.is_available() is False
        assert [c.args[0] for c in cdll.call_args_list] == list(layer_shell._LIB_NAMES)

    def test_a_later_soname_still_counts(self, plugin_dirs):
        _install(plugin_dirs[0])

        def only_the_second(name):
            if name != layer_shell._LIB_NAMES[1]:
                raise OSError("nope")
            return _FakeLib()

        with patch.object(layer_shell.ctypes, "CDLL", side_effect=only_the_second):
            assert layer_shell.is_available() is True


class _FakeLib:
    """Answers to the mangled LayerShellQt::Window symbols the binding needs."""

    def __getattr__(self, name):
        if name.startswith("_ZN12LayerShellQt"):
            return _FakeFn()
        raise AttributeError(name)


class _FakeFn:
    restype = None
    argtypes = ()
