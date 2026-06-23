"""Tests for DesktopAppPinning — resolving an open window to a Kasual app entry.

Filesystem-backed: each test points XDG_DATA_* at a temp ``applications`` dir
holding source ``.desktop`` files and XDG_CONFIG_HOME at a temp Kasual config, so
no real system entries are read or written. Skipped on Windows — Windows uses
WindowsAppPinning (Win32 version-info resolution) with its own behaviour.
"""

import configparser
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Tests the Linux XDG DesktopAppPinning; Windows uses WindowsAppPinning",
)

from domain.catalog.window import Window
from infrastructure.kde.app_pinning import DesktopAppPinning


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    apps = tmp_path / "data" / "applications"
    apps.mkdir(parents=True)
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "data"))   # don't scan /usr
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    return apps, cfg / "kasual-desktop" / "apps"


def _write_source(apps_dir, filename, **keys):
    body = "[Desktop Entry]\nType=Application\n"
    body += "".join(f"{k}={v}\n" for k, v in keys.items())
    (apps_dir / filename).write_text(body)


def _entry(path):
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    cp.read(path)
    return dict(cp["Desktop Entry"])


class TestResolveAndWrite:
    def test_pin_by_desktop_file_name(self, xdg):
        apps, out = xdg
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox %u",
                      Icon="firefox")
        app = DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        assert app is not None
        assert app.name == "Firefox"
        assert app.command == "firefox"      # Exec field code %u stripped
        assert app.icon_theme == "firefox"
        written = list(out.glob("*.desktop"))
        assert len(written) == 1

    def test_reverse_dns_appid_keeps_full_filename(self, xdg):
        # Regression: a reverse-DNS class (org.kde.konsole) must not be truncated
        # to org.kde.desktop — the trailing ".konsole" is not a file extension.
        apps, out = xdg
        _write_source(apps, "org.kde.konsole.desktop", Name="Konsole", Exec="konsole")
        DesktopAppPinning().pin(
            Window(id="w1", title="K", pid=1,
                   desktop_file="org.kde.konsole", resource_class="org.kde.konsole")
        )
        assert (out / "org.kde.konsole.desktop").is_file()

    def test_carries_window_class_for_matching(self, xdg):
        # The window's class is written as StartupWMClass and surfaces on the App,
        # so the pinned tile matches its running window even when the command name
        # (konsole) differs from the class (org.kde.konsole).
        apps, out = xdg
        _write_source(apps, "org.kde.konsole.desktop", Name="Konsole", Exec="konsole")
        app = DesktopAppPinning().pin(
            Window(id="w1", title="K", pid=1,
                   desktop_file="org.kde.konsole", resource_class="org.kde.konsole")
        )
        assert app.wm_class == "org.kde.konsole"
        assert "org.kde.konsole" in app.window_match_keys
        assert _entry(out / "org.kde.konsole.desktop")["StartupWMClass"] == "org.kde.konsole"

    def test_pin_by_startupwmclass(self, xdg):
        apps, out = xdg
        # File name does not match the window class; only StartupWMClass does.
        _write_source(apps, "signal-desktop.desktop", Name="Signal",
                      Exec="signal-desktop", Icon="signal", StartupWMClass="signal")
        app = DesktopAppPinning().pin(
            Window(id="w1", title="Signal", pid=1, desktop_file="", resource_class="signal")
        )
        assert app is not None and app.name == "Signal"

    def test_written_entry_is_kasual_app(self, xdg):
        apps, out = xdg
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox", Icon="firefox")
        DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        entry = _entry(next(out.glob("*.desktop")))
        assert entry["Name"] == "Firefox"
        assert entry["Exec"] == "firefox"
        assert entry["X-Kasual-Order"] == "0"

    def test_order_places_pinned_after_existing(self, xdg):
        apps, out = xdg
        out.mkdir(parents=True)
        (out / "existing-a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (out / "existing-b.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=1\n")
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox")
        DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        pinned = _entry(out / "firefox.desktop")
        assert pinned["X-Kasual-Order"] == "2"   # after the two existing entries

    def test_order_is_past_highest_even_with_a_gap(self, xdg):
        # A prior unpin can leave an order gap (0, _, 2). The pinned tile must sort
        # last (order 3), not reuse a count-based 2 that collides with the existing
        # order-2 entry and would scramble the on-disk vs. live tile index.
        apps, out = xdg
        out.mkdir(parents=True)
        (out / "a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (out / "c.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=C\nExec=c\nX-Kasual-Order=2\n")
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox")
        DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        assert _entry(out / "firefox.desktop")["X-Kasual-Order"] == "3"

    def test_unique_filename_avoids_clobbering(self, xdg):
        apps, out = xdg
        out.mkdir(parents=True)
        (out / "firefox.desktop").write_text("[Desktop Entry]\nType=Application\nName=Old\nExec=old\n")
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox")
        DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        assert (out / "firefox-2.desktop").is_file()
        assert _entry(out / "firefox.desktop")["Name"] == "Old"   # untouched


class TestUnpin:
    def _seed(self, out):
        out.mkdir(parents=True)
        (out / "a.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=A\nExec=a\nX-Kasual-Order=0\n")
        (out / "b.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=B\nExec=b\nX-Kasual-Order=1\n")
        (out / "c.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=C\nExec=c\nX-Kasual-Order=2\n")

    def test_deletes_file_at_index(self, xdg):
        _, out = xdg
        self._seed(out)
        DesktopAppPinning().unpin(1)            # index 1 == order 1 == b.desktop
        remaining = sorted(p.name for p in out.glob("*.desktop"))
        assert remaining == ["a.desktop", "c.desktop"]

    def test_out_of_range_is_noop(self, xdg):
        _, out = xdg
        self._seed(out)
        DesktopAppPinning().unpin(9)
        assert len(list(out.glob("*.desktop"))) == 3

    def test_unpin_then_pin_sorts_last_without_collision(self, xdg):
        apps, out = xdg
        self._seed(out)
        DesktopAppPinning().unpin(1)            # leaves orders 0 and 2 (a gap)
        _write_source(apps, "firefox.desktop", Name="Firefox", Exec="firefox")
        DesktopAppPinning().pin(
            Window(id="w1", title="Moz", pid=1, desktop_file="firefox", resource_class="firefox")
        )
        assert _entry(out / "firefox.desktop")["X-Kasual-Order"] == "3"


class TestFailure:
    def test_no_source_desktop_returns_none(self, xdg):
        app = DesktopAppPinning().pin(
            Window(id="w1", title="X", pid=1, desktop_file="", resource_class="nope")
        )
        assert app is None

    def test_source_without_exec_returns_none(self, xdg):
        apps, out = xdg
        _write_source(apps, "thing.desktop", Name="Thing")   # no Exec
        app = DesktopAppPinning().pin(
            Window(id="w1", title="Thing", pid=1, desktop_file="thing", resource_class="thing")
        )
        assert app is None
        assert not out.exists() or not list(out.glob("*.desktop"))
