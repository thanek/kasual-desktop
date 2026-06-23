"""Tests for the .desktop app loader on Windows — ``config_root()`` under %APPDATA%.

The freedesktop→App mapping rules and the INI parsing are shared with Linux
(covered in ``test_app_config.py`` and ``test_domain_app.py``). Here we verify
the Windows path resolution: ``config_root()`` honours ``%APPDATA%`` (not
``XDG_CONFIG_HOME``) when ``os.name == "nt"``, and the loader, provisioning,
order/color stores all round-trip through ``<APPDATA>/kasual-desktop/apps``.

Skipped on non-Windows: ``config_root()`` branches on ``os.name``; on Linux it
reads ``XDG_CONFIG_HOME`` and ignores ``APPDATA``, so the Windows path branch
can't be exercised there.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Tests Windows config_root() path resolution; needs os.name == 'nt'",
)

from domain.catalog.app import App
from domain.provisioning.candidate import CandidateApp
from infrastructure.common.catalog.app_config import (
    DesktopAppProvisioning, DesktopTileOrderStore, load_apps, provisioned_marker,
)


def _write(directory, filename, content):
    (directory / filename).write_text(content, encoding="utf-8")


@pytest.fixture
def apps_root(tmp_path, monkeypatch):
    """Point %APPDATA% at a temp dir and return the apps directory path.

    Mirrors the Linux ``apps_root`` fixture but for the Windows config root:
    ``config_root()`` returns ``<APPDATA>/kasual-desktop``, so apps live under
    ``<tmp>/kasual-desktop/apps/``. Pre-create the apps dir so individual tests
    can write into it directly."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = tmp_path / "kasual-desktop" / "apps"
    d.mkdir(parents=True)
    return d


# ── config_root / apps_dir / provisioned_marker ──────────────────────────────

class TestConfigRoot:
    def test_config_root_uses_appdata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        from infrastructure.common.catalog.app_config import config_root
        assert config_root() == tmp_path / "kasual-desktop"

    def test_config_root_falls_back_to_home_when_appdata_unset(
        self, tmp_path, monkeypatch
    ):
        # Windows always sets APPDATA, but we guard against an empty env.
        monkeypatch.setenv("APPDATA", "")
        from infrastructure.common.catalog.app_config import config_root
        # Path.home() is patched to a temp dir so the fallback is deterministic.
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert config_root() == tmp_path / "AppData" / "Roaming" / "kasual-desktop"

    def test_apps_dir_under_config_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        from infrastructure.common.catalog.app_config import apps_dir
        assert apps_dir() == tmp_path / "kasual-desktop" / "apps"

    def test_provisioned_marker_under_config_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        from infrastructure.common.catalog.app_config import provisioned_marker
        assert provisioned_marker() == tmp_path / "kasual-desktop" / ".provisioned"


# ── load_apps ─────────────────────────────────────────────────────────────────

class TestLoadApps:
    def test_maps_all_fields(self, apps_root):
        _write(apps_root, "steam.desktop", (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Steam\n"
            "Exec=steam steam://open/bigpicture\n"
            "X-Kasual-Icon=fa5b.steam\n"
            "X-Kasual-Color=#1b2838\n"
            "X-Kasual-RecallMenuTrigger=BTN_MODE_HOLD_1S\n"
            "X-Kasual-HideGraceMs=500\n"
            "X-Kasual-Env=MANGOHUD=1\n"
            "X-Kasual-Order=10\n"
        ))
        apps = load_apps()
        assert len(apps) == 1
        a = apps[0]
        assert a.name == "Steam"
        assert a.command == "steam"
        assert a.args == ("steam://open/bigpicture",)
        assert a.icon == "fa5b.steam"
        assert a.icon_theme is None
        assert a.color == "#1b2838"
        assert a.recall_menu_trigger == "BTN_MODE_HOLD_1S"
        assert a.launch_hide_grace_ms == 500
        assert a.env == {"MANGOHUD": "1"}

    def test_defaults(self, apps_root):
        _write(apps_root, "min.desktop",
               "[Desktop Entry]\nType=Application\nName=Min\nExec=min\n")
        a = load_apps()[0]
        assert a.icon is None
        assert a.icon_theme is None
        assert a.color == "#2e3440"
        assert a.recall_menu_trigger == "BTN_MODE_CLICK"
        assert a.launch_hide_grace_ms == 0
        assert a.env == {}

    def test_icon_theme_used_without_kasual_icon(self, apps_root):
        _write(apps_root, "themed.desktop",
               "[Desktop Entry]\nType=Application\nName=T\nExec=t\nIcon=org.kde.themed\n")
        a = load_apps()[0]
        assert a.icon is None
        assert a.icon_theme == "org.kde.themed"

    def test_order_then_filename(self, apps_root):
        _write(apps_root, "b.desktop",
               "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=20\n")
        _write(apps_root, "a.desktop",
               "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=10\n")
        _write(apps_root, "z.desktop",
               "[Desktop Entry]\nType=Application\nName=Z\nExec=z\n")
        _write(apps_root, "m.desktop",
               "[Desktop Entry]\nType=Application\nName=M\nExec=m\n")
        # Explicit X-Kasual-Order first (A, B); then unordered by filename (m, z).
        assert [a.name for a in load_apps()] == ["A", "B", "M", "Z"]

    def test_skips_nodisplay_hidden_and_non_application(self, apps_root):
        _write(apps_root, "nodisplay.desktop",
               "[Desktop Entry]\nType=Application\nName=N\nExec=n\nNoDisplay=true\n")
        _write(apps_root, "hidden.desktop",
               "[Desktop Entry]\nType=Application\nName=H\nExec=h\nHidden=true\n")
        _write(apps_root, "link.desktop",
               "[Desktop Entry]\nType=Link\nName=L\nURL=http://x\n")
        _write(apps_root, "ok.desktop",
               "[Desktop Entry]\nType=Application\nName=OK\nExec=ok\n")
        assert [a.name for a in load_apps()] == ["OK"]

    def test_skips_missing_name_or_exec(self, apps_root):
        _write(apps_root, "noexec.desktop",
               "[Desktop Entry]\nType=Application\nName=X\n")
        _write(apps_root, "noname.desktop",
               "[Desktop Entry]\nType=Application\nExec=x\n")
        assert list(load_apps()) == []

    def test_bad_file_is_skipped(self, apps_root):
        _write(apps_root, "junk.desktop", "this is not a desktop file at all")
        _write(apps_root, "ok.desktop",
               "[Desktop Entry]\nType=Application\nName=OK\nExec=ok\n")
        assert [a.name for a in load_apps()] == ["OK"]

    def test_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path / "does-not-exist"))
        assert list(load_apps()) == []

    def test_does_not_create_missing_dir(self, tmp_path, monkeypatch):
        # Loading no longer has the side effect of creating the apps dir —
        # that is provisioning's job now.
        monkeypatch.setenv("APPDATA", str(tmp_path))
        load_apps()
        assert not (tmp_path / "kasual-desktop" / "apps").exists()

    def test_windows_exe_path_survives_round_trip(self, apps_root):
        """A Windows command path with backslashes and spaces round-trips through
        the .desktop file: shlex.quote on write, shlex.split on read."""
        _write(apps_root, "edge.desktop", (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Edge\n"
            "Exec='C:\\Program Files\\Microsoft\\msedge.exe'\n"
        ))
        a = load_apps()[0]
        assert a.command == "C:\\Program Files\\Microsoft\\msedge.exe"
        assert a.name == "Edge"


# ── DesktopAppProvisioning ──────────────────────────────────────────────────

class TestDesktopAppProvisioning:
    @pytest.fixture
    def appdata(self, tmp_path, monkeypatch):
        """Point %APPDATA% at a temp dir WITHOUT pre-creating anything."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        return tmp_path

    def _candidate(self):
        return CandidateApp(
            key="steam",
            app=App(
                name="Steam", command="steam", args=("steam://open/bigpicture",),
                icon="fa5b.steam", color="#1b2838",
                recall_menu_trigger="BTN_MODE_HOLD_1S", launch_hide_grace_ms=500,
                categories=("Game",),
            ),
            order=10,
            default_selected=True,
        )

    def test_not_provisioned_before(self, appdata):
        assert DesktopAppProvisioning().is_provisioned() is False

    def test_provision_creates_marker(self, appdata):
        DesktopAppProvisioning().provision([])
        assert provisioned_marker().exists()
        assert DesktopAppProvisioning().is_provisioned() is True

    def test_provision_writes_loadable_desktop_files(self, appdata):
        DesktopAppProvisioning().provision([self._candidate()])

        assert (appdata / "kasual-desktop" / "apps" / "steam.desktop").exists()
        apps = load_apps()
        assert len(apps) == 1
        a = apps[0]
        assert a.name == "Steam"
        assert a.command == "steam"
        assert a.args == ("steam://open/bigpicture",)
        assert a.icon == "fa5b.steam"
        assert a.color == "#1b2838"
        assert a.recall_menu_trigger == "BTN_MODE_HOLD_1S"
        assert a.launch_hide_grace_ms == 500
        assert a.is_game

    def test_empty_provision_yields_empty_catalog_but_marks_done(self, appdata):
        DesktopAppProvisioning().provision([])
        assert list(load_apps()) == []
        assert DesktopAppProvisioning().is_provisioned() is True


# ── DesktopTileOrderStore ───────────────────────────────────────────────────

class TestTileOrderStore:
    def _write_app(self, apps_root, filename, name, order):
        _write(apps_root, filename, (
            "# Kasual Desktop app entry\n"
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={name}\n"
            f"Exec={name.lower()}\n"
            f"X-Kasual-Order={order}\n"
        ))

    def test_swap_reorders_loaded_catalog(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)
        self._write_app(apps_root, "b.desktop", "B", 1)
        self._write_app(apps_root, "c.desktop", "C", 2)

        DesktopTileOrderStore().swap(0, 2)

        assert [a.name for a in load_apps()] == ["C", "B", "A"]

    def test_adjacent_swap_persists(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)
        self._write_app(apps_root, "b.desktop", "B", 1)

        DesktopTileOrderStore().swap(0, 1)

        assert [a.name for a in load_apps()] == ["B", "A"]

    def test_renumbers_sequentially_even_with_shared_orders(self, apps_root):
        # All share order 0 → catalog ties broken by filename: A, B, C.
        self._write_app(apps_root, "a.desktop", "A", 0)
        self._write_app(apps_root, "b.desktop", "B", 0)
        self._write_app(apps_root, "c.desktop", "C", 0)

        DesktopTileOrderStore().swap(0, 1)   # A <-> B

        assert [a.name for a in load_apps()] == ["B", "A", "C"]

    def test_preserves_other_keys(self, apps_root):
        _write(apps_root, "a.desktop", (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=A\n"
            "Exec=a\n"
            "X-Kasual-Color=#123456\n"
            "X-Kasual-Order=0\n"
        ))
        self._write_app(apps_root, "b.desktop", "B", 1)

        DesktopTileOrderStore().swap(0, 1)

        a = next(app for app in load_apps() if app.name == "A")
        assert a.color == "#123456"

    def test_out_of_range_is_a_noop(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)
        DesktopTileOrderStore().swap(0, 5)
        assert [a.name for a in load_apps()] == ["A"]


# ── DesktopTileColorStore ───────────────────────────────────────────────────

class TestTileColorStore:
    def _write_app(self, apps_root, filename, name, order, color=None):
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={name}",
            f"Exec={name.lower()}",
            f"X-Kasual-Order={order}",
        ]
        if color is not None:
            lines.insert(4, f"X-Kasual-Color={color}")
        _write(apps_root, filename, "\n".join(lines) + "\n")

    def test_sets_color_by_render_index(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0, color="#111111")
        self._write_app(apps_root, "b.desktop", "B", 1, color="#222222")

        from infrastructure.common.catalog.app_config import DesktopTileColorStore
        DesktopTileColorStore().set_color(1, "#ff0000")

        apps = {a.name: a for a in load_apps()}
        assert apps["B"].color == "#ff0000"
        assert apps["A"].color == "#111111"

    def test_adds_color_key_when_absent(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)   # no X-Kasual-Color

        from infrastructure.common.catalog.app_config import DesktopTileColorStore
        DesktopTileColorStore().set_color(0, "#abcdef")

        assert load_apps()[0].color == "#abcdef"

    def test_out_of_range_is_a_noop(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0, color="#111111")
        from infrastructure.common.catalog.app_config import DesktopTileColorStore
        DesktopTileColorStore().set_color(5, "#ff0000")
        assert load_apps()[0].color == "#111111"
