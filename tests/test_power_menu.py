"""Tests for the Power split-button logic (PowerMenu) — pure, no Qt.

Covers the sticky-last-choice rule: a power action runs and becomes the new
default, but only once its confirmation is accepted; a cancelled confirm leaves
the previous default untouched.
"""

import pytest

from domain.system.actions import ActionDeps, SLEEP, RESTART, SHUTDOWN
from domain.system.power_menu import PowerMenu


class FakePower:
    def __init__(self):
        self.calls = []

    def suspend(self):  self.calls.append("suspend")
    def reboot(self):   self.calls.append("reboot")
    def poweroff(self): self.calls.append("poweroff")


class FakePrefs:
    def __init__(self, default=SLEEP):
        self._default = default
        self.sets = []

    def default(self):
        return self._default

    def set_default(self, key):
        self.sets.append(key)
        self._default = key


def _accept(_key, execute):
    """A confirm that the user accepts (Yes)."""
    execute()


def _reject(_key, execute):
    """A confirm that the user cancels (No / B) — execute never runs."""


def _menu(confirm, prefs=None):
    power = FakePower()
    prefs = prefs or FakePrefs()
    deps = ActionDeps(desktop=None, power=power)
    return PowerMenu(deps, prefs, confirm), power, prefs


class TestActivateDefault:
    def test_runs_the_stored_default(self):
        menu, power, _ = _menu(_accept, FakePrefs(default=RESTART))
        menu.activate_default()
        assert power.calls == ["reboot"]

    def test_default_key_reads_preference(self):
        menu, _, _ = _menu(_accept, FakePrefs(default=SHUTDOWN))
        assert menu.default_key() == SHUTDOWN


class TestSelectPersistsOnlyOnConfirm:
    def test_accepted_select_runs_and_persists(self):
        menu, power, prefs = _menu(_accept, FakePrefs(default=SLEEP))
        menu.select(SHUTDOWN)
        assert power.calls == ["poweroff"]
        assert prefs.default() == SHUTDOWN          # new default stuck
        assert prefs.sets == [SHUTDOWN]

    def test_cancelled_select_neither_runs_nor_persists(self):
        menu, power, prefs = _menu(_reject, FakePrefs(default=SLEEP))
        menu.select(SHUTDOWN)
        assert power.calls == []
        assert prefs.default() == SLEEP             # unchanged
        assert prefs.sets == []

    def test_persists_before_effect(self):
        # Order matters: Shut Down never returns, so the default must be saved
        # before the effect fires. Assert set_default precedes the power call.
        order = []
        prefs = FakePrefs(default=SLEEP)
        prefs.set_default = lambda k: order.append(("set", k))   # type: ignore
        power = FakePower()
        power.poweroff = lambda: order.append(("effect", "poweroff"))  # type: ignore
        menu = PowerMenu(ActionDeps(desktop=None, power=power), prefs, _accept)
        menu.select(SHUTDOWN)
        assert order == [("set", SHUTDOWN), ("effect", "poweroff")]

    def test_activate_default_accepted_persists_same_default(self):
        menu, power, prefs = _menu(_accept, FakePrefs(default=RESTART))
        menu.activate_default()
        assert power.calls == ["reboot"]
        assert prefs.default() == RESTART

    def test_rejects_non_power_action(self):
        menu, _, _ = _menu(_accept)
        with pytest.raises(ValueError):
            menu.select("volume")
