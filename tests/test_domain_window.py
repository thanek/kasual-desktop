"""Tests for domain.Window matching and recall-trigger inheritance.

Pure rules, no Qt/KWin/proc — the process-parent lookup is injected.
"""

from domain.app import App, TRIGGER_CLICK, TRIGGER_HOLD_1S
from domain.window import Window, resolve_recall_trigger


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


class TestResolveRecallTrigger:
    def _app(self, trigger):
        return App(name="A", command="a", recall_menu_trigger=trigger)

    def test_pid_zero_defaults_to_click(self):
        assert resolve_recall_trigger(0, {}, lambda p: None) == TRIGGER_CLICK

    def test_direct_owner(self):
        apps = {1000: self._app(TRIGGER_HOLD_1S)}
        assert resolve_recall_trigger(1000, apps, lambda p: None) == TRIGGER_HOLD_1S

    def test_inherits_through_parent_chain(self):
        apps = {1000: self._app(TRIGGER_HOLD_1S)}
        parent = {2000: 1000}.get
        assert resolve_recall_trigger(2000, apps, parent) == TRIGGER_HOLD_1S

    def test_unowned_defaults_to_click(self):
        assert resolve_recall_trigger(7777, {}, lambda p: None) == TRIGGER_CLICK

    def test_stops_on_cycle(self):
        # A parent cycle must terminate (visited guard), defaulting to CLICK.
        parent = {5: 6, 6: 5}.get
        assert resolve_recall_trigger(5, {}, parent) == TRIGGER_CLICK

    def test_stops_at_pid_1(self):
        # Walking up to init (pid 1) without an owner → CLICK, no infinite loop.
        parent = {10: 1}.get
        assert resolve_recall_trigger(10, {}, parent) == TRIGGER_CLICK
