"""Tests for the .desktop app loader (system.app_config).

The freedesktop→App mapping rules are tested directly against the domain factory
in test_domain_app.py (TestFromDesktopEntry / Exec / Env). Here we cover the
loader: directory handling, file parsing, ordering and resilience to bad files.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Tests Linux XDG_CONFIG_HOME path handling; Windows uses %APPDATA%",
)

from domain.catalog.app import App
from domain.provisioning.candidate import CandidateApp
from infrastructure.common.catalog.app_config import (
    DesktopAppProvisioning, DesktopTileOrderStore, config_root, load_apps,
    provisioned_marker,
)


def _write(directory, filename, content):
    (directory / filename).write_text(content, encoding="utf-8")


class TestConfigRoot:
    def test_kd_config_dir_is_the_root_itself(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KD_CONFIG_DIR", str(tmp_path))
        assert config_root() == tmp_path

    def test_kd_config_dir_overrides_xdg(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.setenv("KD_CONFIG_DIR", str(tmp_path / "override"))
        assert config_root() == tmp_path / "override"

    def test_falls_back_to_xdg_when_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KD_CONFIG_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert config_root() == tmp_path / "kasual-desktop"


@pytest.fixture
def apps_root(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME at a temp dir and return the apps directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = tmp_path / "kasual-desktop" / "apps"
    d.mkdir(parents=True)
    return d


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

    def test_a_bundled_app_gets_its_identity_back(self, apps_root):
        """A tile written before Kasual's own apps announced an app_id has no
        StartupWMClass, and their windows then look foreign to Kasual."""
        _write(apps_root, "files.desktop", (
            "[Desktop Entry]\nType=Application\nName=File Browser\n"
            "Exec=/usr/share/kasual-desktop/apps/file_browser/file_browser.sh\n"
        ))
        assert load_apps()[0].wm_class == "kasual-file-browser"

    def test_a_stated_identity_is_left_alone(self, apps_root):
        _write(apps_root, "files.desktop", (
            "[Desktop Entry]\nType=Application\nName=File Browser\n"
            "Exec=/opt/mine/apps/file_browser/file_browser.sh\n"
            "StartupWMClass=something-else\n"
        ))
        assert load_apps()[0].wm_class == "something-else"

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
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "does-not-exist"))
        assert list(load_apps()) == []

    def test_does_not_create_missing_dir(self, tmp_path, monkeypatch):
        # Loading no longer has the side effect of creating the apps dir —
        # that is provisioning's job now.
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        load_apps()
        assert not (tmp_path / "kasual-desktop" / "apps").exists()


# ── DesktopAppProvisioning ──────────────────────────────────────────────────

class TestDesktopAppProvisioning:
    @pytest.fixture
    def config_home(self, tmp_path, monkeypatch):
        """Point XDG_CONFIG_HOME at a temp dir WITHOUT pre-creating anything."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
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

    def test_not_provisioned_before(self, config_home):
        assert DesktopAppProvisioning().is_provisioned() is False

    def test_provision_creates_marker(self, config_home):
        DesktopAppProvisioning().provision([])
        assert provisioned_marker().exists()
        assert DesktopAppProvisioning().is_provisioned() is True

    def test_provision_writes_loadable_desktop_files(self, config_home):
        DesktopAppProvisioning().provision([self._candidate()])

        assert (config_home / "kasual-desktop" / "apps" / "steam.desktop").exists()
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

    def test_empty_provision_yields_empty_catalog_but_marks_done(self, config_home):
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


# ── DesktopTileSettingsStore ───────────────────────────────────────────────────

class TestTileSettingsStore:
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

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_color(1, "#ff0000")

        apps = {a.name: a for a in load_apps()}
        assert apps["B"].color == "#ff0000"
        assert apps["A"].color == "#111111"

    def test_adds_color_key_when_absent(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)   # no X-Kasual-Color

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_color(0, "#abcdef")

        assert load_apps()[0].color == "#abcdef"

    def test_out_of_range_is_a_noop(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0, color="#111111")
        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_color(5, "#ff0000")
        assert load_apps()[0].color == "#111111"


# ── DesktopTileSettingsStore.set_recall_trigger ─────────────────────────────────

class TestTileRecallTriggerStore:
    def _write_app(self, apps_root, filename, name, order, trigger=None):
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={name}",
            f"Exec={name.lower()}",
            f"X-Kasual-Order={order}",
        ]
        if trigger is not None:
            lines.insert(4, f"X-Kasual-RecallMenuTrigger={trigger}")
        _write(apps_root, filename, "\n".join(lines) + "\n")

    def test_writes_hold_trigger_when_absent(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0)   # no trigger key

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_recall_trigger(0, "BTN_MODE_HOLD_1S")

        assert load_apps()[0].recall_menu_trigger == "BTN_MODE_HOLD_1S"

    def test_rewrites_existing_hold_trigger(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0, trigger="BTN_MODE_HOLD_1S")

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_recall_trigger(0, "BTN_MODE_CLICK")

        # Default trigger means the key must NOT live in the file.
        text = (apps_root / "a.desktop").read_text(encoding="utf-8")
        assert "X-Kasual-RecallMenuTrigger" not in text
        assert load_apps()[0].recall_menu_trigger == "BTN_MODE_CLICK"

    def test_default_removes_key_even_when_present(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0, trigger="BTN_MODE_HOLD_1S")

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_recall_trigger(0, "BTN_MODE_CLICK")

        text = (apps_root / "a.desktop").read_text(encoding="utf-8")
        assert "X-Kasual-RecallMenuTrigger" not in text

    def test_preserves_other_keys(self, apps_root):
        _write(apps_root, "a.desktop", (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=A\n"
            "Exec=a\n"
            "X-Kasual-Color=#123456\n"
            "X-Kasual-RecallMenuTrigger=BTN_MODE_HOLD_1S\n"
            "X-Kasual-Order=0\n"
        ))

        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_recall_trigger(0, "BTN_MODE_CLICK")

        a = load_apps()[0]
        assert a.color == "#123456"
        assert a.recall_menu_trigger == "BTN_MODE_CLICK"

    def test_out_of_range_is_a_noop(self, apps_root):
        self._write_app(apps_root, "a.desktop", "A", 0,
                        trigger="BTN_MODE_HOLD_1S")
        from infrastructure.common.catalog.app_config import DesktopTileSettingsStore
        DesktopTileSettingsStore().set_recall_trigger(5, "BTN_MODE_CLICK")
        assert load_apps()[0].recall_menu_trigger == "BTN_MODE_HOLD_1S"
