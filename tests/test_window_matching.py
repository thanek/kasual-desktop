"""Characterization tests for the window↔app matching rules.

These pin the *current* behaviour of TileBar's running / managed / trigger-
inheritance logic BEFORE it is extracted to the domain (section H4), then keep
guarding it through the public TileBar surface afterwards. The pure rules get
their own focused unit tests in test_domain_window.py once extracted.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from domain.input.vocabulary import Trigger
from infrastructure.qt.desktop.tile_bar import TileBar
from domain.catalog.app import App
from domain.catalog.window import Window


def _win(id_="1", title="App", pid=0, desktop_file="", resource_class=""):
    return Window(
        id=id_, title=title, pid=pid,
        desktop_file=desktop_file, resource_class=resource_class,
    )


@pytest.fixture
def app_manager():
    mgr = MagicMock()
    mgr.all_running_pids.return_value = []
    mgr.is_running.return_value = False
    mgr.running_idxs.return_value = []
    mgr.running_pid.return_value = None
    return mgr


@pytest.fixture
def apps():
    return [
        App(name="Steam", command="steam", recall_menu_trigger=Trigger.HOLD_1S),
        App(name="Firefox", command="/usr/bin/firefox"),
    ]


@pytest.fixture
def bar(qapp, apps, app_manager):
    return TileBar(apps=apps, app_manager=app_manager)


# ── is_tile_running ──────────────────────────────────────────────────────────

class TestIsTileRunning:
    def test_true_when_app_manager_reports_running(self, bar, app_manager):
        app_manager.is_running.return_value = True
        assert bar.is_tile_running(0, bar._last_windows) is True

    def test_true_on_resource_class_match(self, bar):
        bar.update_windows([_win(resource_class="Steam")])
        assert bar.is_tile_running(0, bar._last_windows) is True       # Steam tile

    def test_true_on_desktop_file_match(self, bar):
        bar.update_windows([_win(resource_class="x", desktop_file="firefox.desktop")])
        assert bar.is_tile_running(1, bar._last_windows) is True       # Firefox tile

    def test_false_when_no_window_matches(self, bar):
        bar.update_windows([_win(resource_class="gedit")])
        assert bar.is_tile_running(0, bar._last_windows) is False
        assert bar.is_tile_running(1, bar._last_windows) is False

    def test_false_with_no_windows(self, bar):
        assert bar.is_tile_running(0, bar._last_windows) is False


# ── Managed-window filtering (windows of our apps don't get a dynamic tile) ──

class TestManagedWindowFiltering:
    # A class/desktopFile match only marks a window managed when it has a real
    # pid — pid==0 windows are never filtered (they always get a dynamic tile).
    def test_window_matching_app_is_excluded(self, bar):
        bar.update_windows([_win(id_="w1", pid=9999, resource_class="Steam")])
        assert bar._dynamic_tiles == []             # represented by the static tile

    def test_unmatched_window_gets_a_dynamic_tile(self, bar):
        bar.update_windows([_win(id_="w1", pid=9999, resource_class="gedit")])
        assert len(bar._dynamic_tiles) == 1

    def test_desktop_file_match_is_excluded(self, bar):
        bar.update_windows([_win(id_="w1", pid=9999, desktop_file="firefox.desktop")])
        assert bar._dynamic_tiles == []

    def test_pid_zero_window_is_never_managed(self, bar):
        # Even with a matching class, a pid==0 window still gets a dynamic tile.
        bar.update_windows([_win(id_="w1", pid=0, resource_class="Steam")])
        assert len(bar._dynamic_tiles) == 1

    def test_pgid_membership_excludes(self, bar, app_manager):
        # A window whose process group is one of our launched apps is managed,
        # even without a class/desktopFile match. POSIX-only: os.getpgid
        # doesn't exist on Windows.
        if not hasattr(os, "getpgid"):
            pytest.skip("os.getpgid is POSIX-only")
        app_manager.all_running_pids.return_value = [4321]
        with patch("infrastructure.qt.desktop.tile_bar.os.getpgid", return_value=4321):
            bar.update_windows([_win(id_="w1", pid=9999, resource_class="mystery")])
        assert bar._dynamic_tiles == []


# ── Recall-trigger inheritance ───────────────────────────────────────────────

class TestFindTriggerForPid:
    def test_pid_zero_defaults_to_click(self, bar):
        assert bar._find_trigger_for_pid(0) == Trigger.CLICK

    def test_owned_pid_inherits_app_trigger(self, bar, app_manager):
        app_manager.running_idxs.return_value = [0]        # Steam (HOLD_1S)
        app_manager.running_pid.side_effect = lambda i: 1000 if i == 0 else None
        assert bar._find_trigger_for_pid(1000) == Trigger.HOLD_1S

    def test_inherits_through_parent_chain(self, bar, app_manager):
        app_manager.running_idxs.return_value = [0]
        app_manager.running_pid.side_effect = lambda i: 1000 if i == 0 else None
        # child 2000 → parent 1000 (owned by Steam) — parent_of is injected now.
        bar._parent_of = lambda pid: 1000
        assert bar._find_trigger_for_pid(2000) == Trigger.HOLD_1S

    def test_unowned_pid_defaults_to_click(self, bar, app_manager):
        app_manager.running_idxs.return_value = []
        bar._parent_of = lambda pid: None
        assert bar._find_trigger_for_pid(7777) == Trigger.CLICK
