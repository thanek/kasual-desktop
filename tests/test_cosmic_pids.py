"""Tests for COSMIC's PID recovery, which no toplevel protocol provides.

The /proc reads are mocked at the process-table seam, so these assert the matching
rules rather than the host's real process list.
"""

from unittest.mock import patch

from infrastructure.cosmic.wm.pids import (
    WindowPidResolver, _named_processes, _normalise, _process_names,
    representative_pid,
)
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.cosmic.wm.xwayland import X11Window


def _toplevel(app_id, title="", identifier="id"):
    return Toplevel(identifier=identifier, title=title, app_id=app_id)


class TestNormalise:
    def test_folds_case_and_punctuation(self):
        assert _normalise("CosmicTerm") == _normalise("cosmic-term") == "cosmicterm"

    def test_keeps_digits(self):
        assert _normalise("steam_app_620") == "steamapp620"


class TestNamedProcesses:
    def test_matches_the_whole_app_id(self):
        assert _named_processes({"bitwarden": {42}}, "bitwarden") == {42}

    def test_falls_back_to_the_last_reverse_dns_segment(self):
        table = {"cosmicterm": {7, 9}}
        assert _named_processes(table, "com.system76.CosmicTerm") == {7, 9}

    def test_unknown_app_id_has_no_candidates(self):
        assert _named_processes({"other": {1}}, "brave-browser") == frozenset()


class TestRepresentativePid:
    def test_a_single_candidate_stands_for_itself(self):
        assert representative_pid(frozenset({99})) == 99

    def test_no_candidates_is_unattributed(self):
        assert representative_pid(frozenset()) == 0

    def test_picks_the_ancestor_the_others_descend_from(self):
        parents = {30: 20, 20: 10, 10: 1}
        with patch("infrastructure.cosmic.wm.pids.parent_pid", parents.get):
            assert representative_pid(frozenset({10, 20, 30})) == 10

    def test_unrelated_instances_stay_unattributed(self):
        parents = {10: 1, 40: 1}
        with patch("infrastructure.cosmic.wm.pids.parent_pid", parents.get):
            assert representative_pid(frozenset({10, 40})) == 0


class TestProcessNames:
    """/proc/<pid>/comm is kernel-truncated to 15 characters, and a truncated name
    matches the wrong app_id outright — cosmic-settings-daemon arrives as exactly
    "cosmic-settings"."""

    def _names(self, comm, exe=None, cmdline=None):
        import io

        def fake_open(path, *args, **kwargs):
            if path.endswith("/comm"):
                return io.StringIO(comm + "\n")
            if path.endswith("/cmdline") and cmdline is not None:
                return io.StringIO(cmdline + "\0")
            raise OSError

        def fake_readlink(path):
            if exe is None:
                raise OSError
            return exe

        with patch("builtins.open", fake_open), \
             patch("infrastructure.cosmic.wm.pids.os.readlink", fake_readlink):
            return list(_process_names(1))

    def test_short_comm_is_used(self):
        assert "cosmic-term" in self._names("cosmic-term")

    def test_truncated_comm_is_dropped(self):
        assert self._names("cosmic-settings") == []

    def test_truncated_comm_falls_back_to_the_real_binary(self):
        names = self._names("cosmic-settings", exe="/usr/bin/cosmic-settings-daemon")
        assert names == ["cosmic-settings-daemon"]

    def test_daemon_no_longer_answers_to_the_app_name(self):
        names = self._names("cosmic-settings", exe="/usr/bin/cosmic-settings-daemon")
        table = {_normalise(n): {1} for n in names}
        assert _named_processes(table, "com.system76.CosmicSettings") == frozenset()

    def test_argv0_is_taken_too(self):
        names = self._names("sh", cmdline="/opt/brave.com/brave/brave")
        assert "brave" in names


class TestResolve:
    def _resolver(self, x11=(), table=None):
        resolver = WindowPidResolver()
        resolver._xwayland.snapshot = lambda: list(x11)
        return resolver, patch("infrastructure.cosmic.wm.pids._process_table",
                               return_value=table or {})

    def test_xwayland_pid_wins_and_is_exact(self):
        x11 = [X11Window(("steam_app_620",), "Game", 500)]
        resolver, table = self._resolver(x11, {"steamapp620": {1, 2}})
        with table:
            resolved = resolver.resolve([_toplevel("steam_app_620", "Game", "a")])
        assert resolved == {"a": frozenset({500})}

    def test_falls_back_to_the_process_table(self):
        resolver, table = self._resolver(table={"cosmicterm": {7, 9}})
        with table:
            resolved = resolver.resolve([_toplevel("com.system76.CosmicTerm", "", "a")])
        assert resolved == {"a": frozenset({7, 9})}

    def test_unresolvable_window_is_absent(self):
        resolver, table = self._resolver(table={"other": {1}})
        with table:
            assert resolver.resolve([_toplevel("brave-browser", "", "a")]) == {}

    def test_process_table_is_read_once_for_many_windows(self):
        resolver = WindowPidResolver()
        resolver._xwayland.snapshot = lambda: []
        with patch("infrastructure.cosmic.wm.pids._process_table",
                   return_value={}) as table:
            resolver.resolve([_toplevel("a", identifier="1"),
                              _toplevel("b", identifier="2")])
        table.assert_called_once()

    def test_process_table_is_not_read_when_x11_answers_everything(self):
        resolver = WindowPidResolver()
        resolver._xwayland.snapshot = lambda: [X11Window(("game",), "G", 5)]
        with patch("infrastructure.cosmic.wm.pids._process_table") as table:
            resolver.resolve([_toplevel("game", "G", "a")])
        table.assert_not_called()
