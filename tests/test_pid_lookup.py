"""Tests for resolving a Wayland app id to a process, against a fake /proc."""

import os

import pytest

from infrastructure.linux.wayland.pid_lookup import (
    AppIdPidResolver, ProcessNames, app_id_keys, match_pid,
)


@pytest.fixture
def proc(tmp_path):
    def add(pid: int, comm: str = "", cmdline: str = "", exe: str = "") -> None:
        directory = tmp_path / str(pid)
        directory.mkdir()
        if comm:
            (directory / "comm").write_text(f"{comm}\n")
        if cmdline:
            (directory / "cmdline").write_text("\0".join(cmdline.split()) + "\0")
        if exe:
            os.symlink(exe, directory / "exe")

    add.root = str(tmp_path)
    return add


class TestAppIdKeys:
    def test_a_plain_id_is_its_own_key(self):
        assert app_id_keys("firefox") == ["firefox"]

    def test_a_reverse_dns_id_also_yields_its_last_component(self):
        assert app_id_keys("org.gnome.Nautilus") == ["org.gnome.nautilus", "nautilus"]

    def test_the_desktop_suffix_is_dropped(self):
        assert app_id_keys("firefox-esr.desktop") == ["firefox-esr"]


class TestProcessNames:
    def test_reads_comm_cmdline_and_exe(self, proc):
        proc(42, comm="kitty", cmdline="/usr/bin/kitty --single", exe="/usr/bin/kitty")
        names = ProcessNames(proc.root)
        names.scan()
        assert names.names[42] == {"kitty"}

    def test_a_wrapper_script_contributes_both_names(self, proc):
        proc(7, comm="steam", cmdline="/home/pi/.steam/steam.sh")
        names = ProcessNames(proc.root)
        names.scan()
        assert names.names[7] == {"steam", "steam.sh"}

    def test_non_numeric_entries_are_skipped(self, proc, tmp_path):
        (tmp_path / "self").mkdir()
        proc(9, comm="labwc")
        names = ProcessNames(proc.root)
        names.scan()
        assert list(names.names) == [9]


class TestMatchPid:
    def test_an_exact_name_wins_over_a_substring(self):
        names = {10: {"steamwebhelper"}, 20: {"steam"}}
        assert match_pid(["steam"], names) == 20

    def test_a_truncated_comm_still_matches(self):
        names = {30: {"gnome-calculato"}}
        assert match_pid(["gnome-calculator"], names) == 30

    def test_the_lowest_pid_settles_a_tie(self):
        names = {50: {"chromium"}, 40: {"chromium"}}
        assert match_pid(["chromium"], names) == 40

    def test_nothing_matching_is_no_pid(self):
        assert match_pid(["nautilus"], {10: {"labwc"}}) == 0


class TestResolver:
    def test_resolves_an_app_id_to_its_process(self, proc):
        proc(101, comm="firefox-esr", exe="/usr/lib/firefox-esr/firefox-esr")
        resolver = AppIdPidResolver(proc.root)
        assert resolver.resolve(["firefox-esr"]) == {"firefox-esr": 101}

    def test_an_unmatched_id_resolves_to_zero(self, proc):
        proc(101, comm="labwc")
        resolver = AppIdPidResolver(proc.root)
        assert resolver.resolve(["kitty"]) == {"kitty": 0}

    def test_a_second_lookup_does_not_rescan(self, proc):
        proc(101, comm="kitty")
        resolver = AppIdPidResolver(proc.root)
        resolver.resolve(["kitty"])
        scans = []
        resolver._processes.scan = lambda: scans.append(True)
        assert resolver.resolve(["kitty"]) == {"kitty": 101}
        assert scans == []

    def test_an_unmatched_id_is_retried_once_the_process_appears(self, proc):
        resolver = AppIdPidResolver(proc.root, rescan_interval_s=0)
        assert resolver.resolve(["kitty"]) == {"kitty": 0}
        proc(202, comm="kitty")
        assert resolver.resolve(["kitty"]) == {"kitty": 202}

    def test_a_rescan_is_rate_limited(self, proc):
        resolver = AppIdPidResolver(proc.root, rescan_interval_s=60)
        resolver.resolve(["kitty"])
        proc(202, comm="kitty")
        assert resolver.resolve(["kitty"]) == {"kitty": 0}

    def test_a_dead_process_is_dropped_and_looked_up_again(self, proc, tmp_path):
        proc(303, comm="kitty")
        resolver = AppIdPidResolver(proc.root, rescan_interval_s=0)
        assert resolver.resolve(["kitty"]) == {"kitty": 303}

        for entry in (tmp_path / "303").iterdir():
            entry.unlink()
        (tmp_path / "303").rmdir()
        proc(404, comm="kitty")
        assert resolver.resolve(["kitty"]) == {"kitty": 404}

    def test_an_empty_app_id_resolves_to_zero(self, proc):
        assert AppIdPidResolver(proc.root).resolve([""]) == {"": 0}
