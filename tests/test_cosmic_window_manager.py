"""Tests for the COSMIC WindowManager adapter: the mapping to domain windows and
the routing of the port's operations. The protocol mirror, the PID recovery and the
X11 table are stubbed — they have tests of their own.
"""

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.cosmic.wm.toplevels import Toplevel


class FakeMirror:
    """Stands in for CosmicToplevels, recording the operations it is asked for."""

    def __init__(self, toplevels=()):
        self._toplevels = list(toplevels)
        self.activated: list[int] = []
        self.minimized: list[int] = []
        self.closed: list[int] = []

    def toplevels(self):
        return list(self._toplevels)

    def handle_for(self, identifier):
        for index, toplevel in enumerate(self._toplevels):
            if toplevel.identifier == identifier:
                return 100 + index
        return None

    def activate(self, handle):
        self.activated.append(handle)

    def minimize(self, handle):
        self.minimized.append(handle)

    def close_window(self, handle):
        self.closed.append(handle)


def _toplevel(identifier, app_id, title="", **state):
    return Toplevel(identifier=identifier, app_id=app_id, title=title, **state)


@pytest.fixture
def manager_for(qapp):
    """Builds a CosmicWindowManager over a FakeMirror and fixed PID candidates."""
    def build(toplevels, candidates=None):
        from infrastructure.cosmic.wm.window_manager import CosmicWindowManager

        mirror = FakeMirror(toplevels)
        xwayland = MagicMock()
        xwayland.snapshot.return_value = []
        client = MagicMock()
        with patch("infrastructure.cosmic.wm.window_manager.CosmicToplevels",
                   return_value=mirror), \
             patch("infrastructure.cosmic.wm.window_manager.XWaylandWindows",
                   return_value=xwayland):
            wm = CosmicWindowManager(client)
        wm._pids.resolve = lambda _toplevels, _x11: dict(candidates or {})
        wm._do_refresh()
        return wm, mirror, client
    return build


class TestEnumWindows:
    def test_maps_a_toplevel_to_a_domain_window(self, manager_for):
        wm, _, _client = manager_for(
            [_toplevel("id-a", "firefox", "Firefox", activated=True)],
            {"id-a": frozenset({500})})
        window = wm.cached_windows()[0]
        assert (window.id, window.title, window.pid, window.active,
                window.resource_class) == ("id-a", "Firefox", 500, True, "firefox")

    def test_fullscreen_state_is_carried_over(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "game", fullscreen=True)])
        assert wm.cached_windows()[0].fullscreen is True

    def test_unresolvable_pid_is_zero(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "brave-browser")])
        assert wm.cached_windows()[0].pid == 0

    def test_ambiguous_candidates_leave_the_pid_unattributed(self, manager_for):
        with patch("infrastructure.cosmic.wm.pids.parent_pid", {10: 1, 40: 1}.get):
            wm, _, _client = manager_for([_toplevel("id-a", "term")],
                                {"id-a": frozenset({10, 40})})
        assert wm.cached_windows()[0].pid == 0

    def test_toplevel_without_an_app_id_is_skipped(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "")])
        assert wm.cached_windows() == []

    def test_toplevel_before_its_identifier_arrives_is_skipped(self, manager_for):
        wm, _, _client = manager_for([_toplevel("", "firefox")])
        assert wm.cached_windows() == []

    def test_our_own_window_is_skipped(self, manager_for):
        import os
        wm, _, _client = manager_for([_toplevel("id-a", "some-app")],
                            {"id-a": frozenset({os.getpid()})})
        assert wm.cached_windows() == []

    def test_our_own_surfaces_are_skipped_by_app_id(self, manager_for, qapp):
        # COSMIC will not report our own PID, so a surface of ours that is not
        # layer-shell would otherwise earn itself a tile.
        qapp.setDesktopFileName("kasual-desktop")
        wm, _, _client = manager_for([_toplevel("id-a", "kasual-desktop", "Kasual Home"),
                             _toplevel("id-b", "kasual-desktop", "Kasual Hints"),
                             _toplevel("id-c", "firefox", "Firefox")])
        assert [w.resource_class for w in wm.cached_windows()] == ["firefox"]

    def test_one_x11_scan_serves_the_whole_refresh(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "firefox")])
        assert wm._xwayland.snapshot.call_count == 1

    def test_a_refresh_asks_for_the_fullscreen_a_game_never_asked_for(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "game")])
        wm._fullscreen = MagicMock()
        wm._xwayland.snapshot.return_value = ["the x11 table"]
        wm._do_refresh()
        wm._fullscreen.apply.assert_called_once_with(
            [_toplevel("id-a", "game")], ["the x11 table"])

    def test_active_window_id_follows_the_activated_toplevel(self, manager_for):
        wm, _, _client = manager_for([_toplevel("id-a", "firefox"),
                             _toplevel("id-b", "term", activated=True)])
        assert wm.get_active_window_id() == "id-b"


class TestOperations:
    def test_activate_and_close_route_to_the_handle(self, manager_for):
        wm, mirror, _client = manager_for([_toplevel("id-a", "firefox"),
                                  _toplevel("id-b", "term")])
        wm.activate_window("id-b")
        wm.close_window("id-a")
        assert (mirror.activated, mirror.closed) == ([101], [100])

    def test_unknown_window_is_a_no_op(self, manager_for):
        wm, mirror, _client = manager_for([_toplevel("id-a", "firefox")])
        wm.activate_window("nobody")
        wm.close_window("nobody")
        assert (mirror.activated, mirror.closed) == ([], [])

    def test_minimize_covers_every_window_of_the_launched_tree(self, manager_for):
        wm, mirror, _client = manager_for(
            [_toplevel("id-a", "game"), _toplevel("id-b", "game"),
             _toplevel("id-c", "other")],
            {"id-a": frozenset({11}), "id-b": frozenset({12}),
             "id-c": frozenset({99})})
        with patch("infrastructure.cosmic.wm.window_manager.expand_pid_tree",
                   return_value={10, 11, 12}):
            wm.minimize_windows_for_pids({10})
        assert sorted(mirror.minimized) == [100, 101]

    def test_activate_for_pids_reaches_a_window_with_no_single_pid(self, manager_for):
        # A second instance of a running program: membership of the tree answers
        # what a single PID cannot.
        wm, mirror, _client = manager_for([_toplevel("id-a", "term")],
                                 {"id-a": frozenset({10, 40})})
        assert wm.cached_windows()[0].pid == 0
        with patch("infrastructure.cosmic.wm.window_manager.expand_pid_tree",
                   return_value={40, 41}):
            wm.activate_windows_for_pids({40})
        assert mirror.activated == [100]

    def test_windows_outside_the_tree_are_left_alone(self, manager_for):
        wm, mirror, _client = manager_for([_toplevel("id-a", "other")],
                                 {"id-a": frozenset({99})})
        with patch("infrastructure.cosmic.wm.window_manager.expand_pid_tree",
                   return_value={10}):
            wm.minimize_windows_for_pids({10})
        assert mirror.minimized == []

    def test_raise_for_pid_exact_does_not_expand_the_tree(self, manager_for):
        wm, mirror, _client = manager_for(
            [_toplevel("id-a", "game"), _toplevel("id-b", "other")],
            {"id-a": frozenset({11}), "id-b": frozenset({12})})
        wm.raise_windows_for_pid_exact(11)
        assert mirror.activated == [100]

    def test_handing_an_app_the_screen_is_told_to_the_fullscreen_rule(self, manager_for):
        wm, _, _client = manager_for([])
        wm._fullscreen = MagicMock()
        wm.screen_given_to_app()
        wm._fullscreen.screen_given_to_app.assert_called_once()

    def test_activating_a_window_hands_it_the_screen_too(self, manager_for):
        # How the Home Menu returns to a running app, rather than through a launch.
        wm, _, _client = manager_for([_toplevel("id-a", "game")])
        wm._fullscreen = MagicMock()
        wm.activate_window("id-a")
        wm._fullscreen.screen_given_to_app.assert_called_once()

    def test_kasual_taking_the_screen_back_ends_it(self, manager_for):
        wm, _, _client = manager_for([])
        wm._fullscreen = MagicMock()
        wm.raise_self()
        wm._fullscreen.screen_taken_back.assert_called_once()

    def test_close_disposes_the_connection(self, manager_for):
        wm, _mirror, client = manager_for([])
        wm.close()
        client.close.assert_called_once()
