"""Tests for domain.Window matching and recall-trigger inheritance.

Pure rules, no Qt/KWin/proc — the process-parent lookup is injected.
"""

from domain.catalog.app import App
from domain.catalog.target import AppTarget, WindowTarget, target_at_index
from domain.catalog.window import Window
from domain.catalog.window_rules import (
    active_unmanaged_window, app_window_present, descends_from_launcher,
    external_windows, resolve_recall_trigger,
)
from domain.input.vocabulary import Trigger


def _win(resource_class="", desktop_file="", pid=0):
    return Window(id="w", title="t", pid=pid,
                  resource_class=resource_class, desktop_file=desktop_file)


class TestMatchesApp:
    def test_resource_class_match_case_insensitive(self):
        app = App(name="Steam", command="steam")
        assert _win(resource_class="Steam").matches_app(app) is True

    def test_desktop_file_basename_match(self):
        app = App(name="Firefox", command="/usr/bin/firefox")
        assert _win(desktop_file="firefox.desktop").matches_app(app) is True

    def test_no_match(self):
        app = App(name="Steam", command="steam")
        assert _win(resource_class="gedit", desktop_file="org.gnome.gedit").matches_app(app) is False

    def test_empty_window_does_not_match(self):
        app = App(name="Steam", command="steam")
        assert _win().matches_app(app) is False


class TestExternalWindows:
    """Which open windows deserve a dynamic tile (not already a static app tile)."""

    APPS = [App(name="Steam", command="steam")]

    def _never_owned(self, w):
        return False

    def test_unmatched_window_is_external(self):
        win = _win(resource_class="gedit", pid=9999)
        assert external_windows([win], self.APPS, self._never_owned) == [win]

    def test_window_matching_an_app_is_not_external(self):
        win = _win(resource_class="Steam", pid=9999)
        assert external_windows([win], self.APPS, self._never_owned) == []

    def test_window_owned_by_running_group_is_not_external(self):
        win = _win(resource_class="mystery", pid=9999)
        assert external_windows([win], self.APPS, lambda w: True) == []

    def test_pid_zero_window_is_always_external(self):
        # Even matching an app's class, a pid==0 window still earns a tile.
        win = _win(resource_class="Steam", pid=0)
        assert external_windows([win], self.APPS, self._never_owned) == [win]

    def test_preserves_order_and_filters_mix(self):
        ext1 = _win(resource_class="gedit", pid=1)
        managed = _win(resource_class="Steam", pid=2)
        ext2 = _win(resource_class="vlc", pid=3)
        assert external_windows([ext1, managed, ext2], self.APPS, self._never_owned) == [ext1, ext2]


class TestActiveUnmanagedWindow:
    """The active window that matches no configured app — e.g. a Steam game."""

    APPS = [App(name="Steam", command="steam")]

    def test_active_window_matching_no_app(self):
        game = Window(id="g", title="Game", pid=200, active=True,
                      resource_class="steam_app_1")
        assert active_unmanaged_window([game], self.APPS) == game

    def test_active_window_matching_an_app_is_managed(self):
        own = Window(id="s", title="Steam", pid=100, active=True,
                     resource_class="steam")
        assert active_unmanaged_window([own], self.APPS) is None

    def test_no_active_window(self):
        win = Window(id="g", title="Game", pid=200, active=False,
                     resource_class="steam_app_1")
        assert active_unmanaged_window([win], self.APPS) is None

    def test_active_pid_zero_window_is_ignored(self):
        win = Window(id="g", title="Game", pid=0, active=True,
                     resource_class="steam_app_1")
        assert active_unmanaged_window([win], self.APPS) is None

    def test_picks_active_among_many(self):
        bg   = Window(id="s", title="Steam", pid=100, active=False, resource_class="steam")
        game = Window(id="g", title="Game", pid=200, active=True, resource_class="steam_app_1")
        assert active_unmanaged_window([bg, game], self.APPS) == game


class TestAppWindowPresent:
    """Has a just-launched app already mapped a window? (defer-hide rule)."""

    APP = App(name="Foo", command="/usr/bin/foo")   # command_basename == "foo"

    def test_present_by_owned_pid_subtree(self):
        win = Window(id="w", title="t", pid=1001)
        assert app_window_present([win], self.APP, {1000, 1001}) is True

    def test_present_by_resource_class(self):
        win = Window(id="w", title="t", pid=9, resource_class="foo")
        assert app_window_present([win], self.APP, set()) is True

    def test_present_by_desktop_file(self):
        win = Window(id="w", title="t", pid=9, desktop_file="foo.desktop")
        assert app_window_present([win], self.APP, set()) is True

    def test_absent_when_neither_pid_nor_identity(self):
        win = Window(id="w", title="t", pid=9, resource_class="bar", desktop_file="baz.desktop")
        assert app_window_present([win], self.APP, set()) is False

    def test_absent_with_no_windows(self):
        assert app_window_present([], self.APP, {1000}) is False


class TestTargetAtIndex:
    """Foreground Target at a tile position: static apps first, then windows."""

    APPS = [App(name="Steam", command="steam"), App(name="Firefox", command="firefox")]
    WINS = [Window(id="w1", title="Doc", pid=1000),
            Window(id="w2", title="Video", pid=2000)]

    def _no_trigger(self, pid):
        return Trigger.CLICK

    def test_static_index_yields_app_target(self):
        assert target_at_index(1, self.APPS, self.WINS, self._no_trigger) == \
            AppTarget(index=1, name="Firefox")

    def test_dynamic_index_yields_window_target(self):
        # index 2 == first window (after 2 static apps)
        assert target_at_index(2, self.APPS, self.WINS, self._no_trigger) == \
            WindowTarget(window_id="w1", name="Doc", trigger=Trigger.CLICK, pid=1000)

    def test_window_target_carries_resolved_trigger(self):
        trigger_for = lambda pid: Trigger.HOLD_1S if pid == 2000 else Trigger.CLICK
        target = target_at_index(3, self.APPS, self.WINS, trigger_for)  # w2, pid 2000
        assert target == WindowTarget(
            window_id="w2", name="Video", trigger=Trigger.HOLD_1S, pid=2000)

    def test_out_of_range_yields_none(self):
        assert target_at_index(4, self.APPS, self.WINS, self._no_trigger) is None

    def test_empty_yields_none(self):
        assert target_at_index(0, [], [], self._no_trigger) is None


class TestResolveRecallTrigger:
    def _app(self, trigger):
        return App(name="A", command="a", recall_menu_trigger=trigger)

    def test_pid_zero_defaults_to_click(self):
        assert resolve_recall_trigger(0, {}, lambda p: None) == Trigger.CLICK

    def test_direct_owner(self):
        apps = {1000: self._app(Trigger.HOLD_1S)}
        assert resolve_recall_trigger(1000, apps, lambda p: None) == Trigger.HOLD_1S

    def test_inherits_through_parent_chain(self):
        apps = {1000: self._app(Trigger.HOLD_1S)}
        parent = {2000: 1000}.get
        assert resolve_recall_trigger(2000, apps, parent) == Trigger.HOLD_1S

    def test_unowned_defaults_to_click(self):
        assert resolve_recall_trigger(7777, {}, lambda p: None) == Trigger.CLICK

    def test_stops_on_cycle(self):
        # A parent cycle must terminate (visited guard), defaulting to CLICK.
        parent = {5: 6, 6: 5}.get
        assert resolve_recall_trigger(5, {}, parent) == Trigger.CLICK

    def test_stops_at_pid_1(self):
        # Walking up to init (pid 1) without an owner → CLICK, no infinite loop.
        parent = {10: 1}.get
        assert resolve_recall_trigger(10, {}, parent) == Trigger.CLICK


class TestDescendsFromLauncher:
    def test_direct_launcher_process(self):
        names = {1000: "steam"}.get
        assert descends_from_launcher(1000, names, lambda p: None) is True

    def test_game_under_steam_reaper(self):
        # KCD.exe → wine → pressure-vessel → reaper → steam; matched at reaper.
        names = {500: "KCD.exe", 400: "wine64-preloade", 300: "reaper", 200: "steam"}.get
        parent = {500: 400, 400: 300, 300: 200, 200: 1}.get
        assert descends_from_launcher(500, names, parent) is True

    def test_wine_prefix_matches(self):
        names = {700: "wineserver"}.get
        assert descends_from_launcher(700, names, lambda p: None) is True

    def test_heroic_launched_game(self):
        names = {800: "Game", 600: "heroic"}.get
        parent = {800: 600, 600: 1}.get
        assert descends_from_launcher(800, names, parent) is True

    def test_plain_app_is_not_a_game(self):
        # A browser under the shell — no launcher in the chain.
        names = {900: "firefox", 100: "plasmashell"}.get
        parent = {900: 100, 100: 1}.get
        assert descends_from_launcher(900, names, parent) is False

    def test_unknown_name_defaults_false(self):
        assert descends_from_launcher(123, lambda p: None, lambda p: None) is False

    def test_stops_on_cycle(self):
        names = lambda p: "x"
        parent = {5: 6, 6: 5}.get
        assert descends_from_launcher(5, names, parent) is False
