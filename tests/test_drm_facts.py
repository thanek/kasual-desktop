"""Tests for LinuxSystemFacts — CDM discovery and the machine's traits."""

import ast
import os
from pathlib import Path

import pytest

from infrastructure.linux.drm import facts as facts_module
from infrastructure.linux.drm.facts import LinuxSystemFacts

_REPO = Path(__file__).resolve().parents[1]
_FACTS_SOURCE = _REPO / "src/infrastructure/linux/drm/facts.py"
_NETFLIX_SOURCE = _REPO / "apps/netflix/src/netflix.py"

_CHROME_GLOB = "chrome/*/_platform_specific/linux_*/libwidevinecdm.so"
_INSTALLER_GLOB = "widevine/_platform_specific/linux_*/libwidevinecdm.so"


def _module(root: Path, relative: str, *, size: int = 64, mtime: float = 1000.0):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    os.utime(path, (mtime, mtime))
    return path


def _globs(monkeypatch, root: Path, *patterns: str) -> None:
    monkeypatch.setattr(
        facts_module, "_CDM_GLOBS", tuple(str(root / p) for p in patterns))


def _arch(monkeypatch, machine: str) -> None:
    monkeypatch.setattr(facts_module.platform, "machine", lambda: machine)


def _literal(source: Path, name: str):
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        targets = getattr(node, "targets", [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not assigned at module level in {source}")


class TestFindingTheModule:
    def test_picks_the_module_for_this_architecture(self, tmp_path, monkeypatch):
        _module(tmp_path, "widevine/_platform_specific/linux_x64/libwidevinecdm.so")
        wanted = _module(
            tmp_path, "widevine/_platform_specific/linux_arm/libwidevinecdm.so")
        _globs(monkeypatch, tmp_path, _INSTALLER_GLOB)
        _arch(monkeypatch, "armv7l")
        assert LinuxSystemFacts().cdm_path() == str(wanted)

    def test_an_architecture_with_no_known_layout_finds_nothing(
        self, tmp_path, monkeypatch
    ):
        _module(tmp_path, "widevine/_platform_specific/linux_x64/libwidevinecdm.so")
        _globs(monkeypatch, tmp_path, _INSTALLER_GLOB)
        _arch(monkeypatch, "riscv64")
        assert LinuxSystemFacts().cdm_path() is None

    def test_the_newest_module_wins_where_version_names_do_not_sort(
        self, tmp_path, monkeypatch
    ):
        _module(tmp_path, "chrome/4.10.9/_platform_specific/linux_x64/"
                          "libwidevinecdm.so", mtime=2000.0)
        newest = _module(tmp_path, "chrome/4.10.10/_platform_specific/linux_x64/"
                                   "libwidevinecdm.so", mtime=3000.0)
        _globs(monkeypatch, tmp_path, _CHROME_GLOB)
        _arch(monkeypatch, "x86_64")
        assert LinuxSystemFacts().cdm_path() == str(newest)

    def test_an_earlier_glob_outranks_a_newer_file(self, tmp_path, monkeypatch):
        installed = _module(
            tmp_path, "widevine/_platform_specific/linux_x64/libwidevinecdm.so",
            mtime=1000.0)
        _module(tmp_path, "chrome/4.10.9/_platform_specific/linux_x64/"
                          "libwidevinecdm.so", mtime=9000.0)
        _globs(monkeypatch, tmp_path, _INSTALLER_GLOB, _CHROME_GLOB)
        _arch(monkeypatch, "x86_64")
        assert LinuxSystemFacts().cdm_path() == str(installed)

    def test_the_empty_stub_is_not_a_module(self, tmp_path, monkeypatch):
        _module(tmp_path, "widevine/_platform_specific/linux_x64/"
                          "libwidevinecdm.so", size=0)
        _globs(monkeypatch, tmp_path, _INSTALLER_GLOB)
        _arch(monkeypatch, "x86_64")
        assert LinuxSystemFacts().cdm_path() is None

    def test_a_symlink_leading_nowhere_is_not_a_module(self, tmp_path, monkeypatch):
        link = tmp_path / "widevine/_platform_specific/linux_x64"
        link.mkdir(parents=True)
        (link / "libwidevinecdm.so").symlink_to(tmp_path / "gone.so")
        _globs(monkeypatch, tmp_path, _INSTALLER_GLOB)
        _arch(monkeypatch, "x86_64")
        assert LinuxSystemFacts().cdm_path() is None

    def test_a_layout_without_an_architecture_directory_still_counts(
        self, tmp_path, monkeypatch
    ):
        firefox = _module(tmp_path, "firefox/p1/gmp-widevinecdm/4.10.2/"
                                    "libwidevinecdm.so")
        _globs(monkeypatch, tmp_path, "firefox/*/gmp-widevinecdm/*/libwidevinecdm.so")
        _arch(monkeypatch, "aarch64")
        assert LinuxSystemFacts().cdm_path() == str(firefox)


class TestTraits:
    @pytest.fixture(autouse=True)
    def _nothing_special(self, tmp_path, monkeypatch):
        monkeypatch.setattr(facts_module, "_OSTREE_MARKER", tmp_path / "absent")
        monkeypatch.setattr(facts_module, "_DEVICE_TREE_MODEL", tmp_path / "absent")

    def test_a_plain_machine_has_no_traits(self):
        assert LinuxSystemFacts().machine().traits == ()

    def test_an_ostree_deployment_is_recognised(self, tmp_path, monkeypatch):
        marker = tmp_path / "ostree-booted"
        marker.touch()
        monkeypatch.setattr(facts_module, "_OSTREE_MARKER", marker)
        assert LinuxSystemFacts().machine().traits == ("ostree",)

    def test_the_board_comes_from_the_device_tree(self, tmp_path, monkeypatch):
        model = tmp_path / "model"
        model.write_bytes(b"Raspberry Pi 5 Model B Rev 1.0\x00")
        monkeypatch.setattr(facts_module, "_DEVICE_TREE_MODEL", model)
        assert LinuxSystemFacts().machine().traits == ("raspberrypi",)

    def test_other_boards_are_not_mistaken_for_a_pi(self, tmp_path, monkeypatch):
        model = tmp_path / "model"
        model.write_bytes(b"Apple MacBook Pro (13-inch, M1, 2020)\x00")
        monkeypatch.setattr(facts_module, "_DEVICE_TREE_MODEL", model)
        assert LinuxSystemFacts().machine().traits == ()


class TestBundledAppParity:
    """apps/netflix runs as its own process and imports nothing from src, so it
    carries copies of these two tables. Copies are worth having only while they
    are equal."""

    def test_the_glob_lists_are_the_same(self):
        assert (_literal(_NETFLIX_SOURCE, "_CDM_GLOBS")
                == _literal(_FACTS_SOURCE, "_CDM_GLOBS"))

    def test_the_architecture_tables_are_the_same(self):
        assert (_literal(_NETFLIX_SOURCE, "_ARCH_DIRS")
                == _literal(_FACTS_SOURCE, "_ARCH_DIRS"))
