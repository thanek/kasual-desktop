"""Tests for wlr-layer-shell as a setup requirement: what the probe reads out of
this Qt, which recipe each kind of machine is sent down, and that the card lets
the user through — a scattered interface is still usable, and nothing installed
now could reach a process whose shell integration is already bound.

Neither LayerShellQt nor a compositor is contacted; only the two lookups the
probe makes are stubbed.
"""

from unittest.mock import patch

import pytest

from domain.preflight.layer_shell import (
    NO_LIBRARY, NO_PLUGIN, LayerShellProbe, LayerShellState, LayerShellSurfaces,
)
from domain.preflight.layer_shell_recipes import PACKAGE, all_recipes
from domain.setup.gate import SetupGate
from domain.setup.plan import MachineProfile, Readiness
from domain.setup.readiness import SetupReadiness

_MODULE = "infrastructure.linux.wayland.layer_shell_probe.layer_shell"


class _Facts:
    def __init__(self, machine: MachineProfile) -> None:
        self._machine = machine

    def machine(self) -> MachineProfile:
        return self._machine

    def has_command(self, name: str) -> bool:
        return False

    def path_exists(self, pattern: str) -> bool:
        return False


class _Probe(LayerShellProbe):
    def __init__(self, state: LayerShellState) -> None:
        self._state = state

    def state(self) -> LayerShellState:
        return self._state


class _View:
    def __init__(self) -> None:
        self.reports = []

    def present(self, report, on_recheck, on_done, on_abort, on_remedy, probe=None):
        self.reports.append(report)
        self.on_done = on_done
        self.on_abort = on_abort


def _report(state, distro="fedora", arch="x86_64"):
    return SetupReadiness(
        LayerShellSurfaces(_Probe(state)),
        _Facts(MachineProfile(arch=arch, distro_id=distro)),
        all_recipes(),
    ).report()


class TestProbe:
    def _state(self, *, plugin, library):
        from infrastructure.linux.wayland.layer_shell_probe import QtLayerShellProbe

        with patch(f"{_MODULE}.integration_plugin",
                   return_value="/usr/lib/qt6/…/liblayer-shell.so" if plugin else None), \
             patch(f"{_MODULE}.is_available", return_value=library):
            return QtLayerShellProbe().state()

    def test_both_halves_present_is_ready(self):
        assert self._state(plugin=True, library=True) is LayerShellState.READY

    def test_no_plugin_for_this_qt(self):
        # The Qt 5-only packaging every Debian-family distribution still ships.
        assert self._state(plugin=False, library=True) is LayerShellState.NO_PLUGIN

    def test_plugin_without_its_library(self):
        assert self._state(plugin=True, library=False) is LayerShellState.NO_LIBRARY


class TestReadiness:
    def test_a_working_layer_shell_needs_no_card(self):
        assert _report(LayerShellState.READY).state is Readiness.READY

    def test_a_missing_plugin_carries_the_trait(self):
        report = _report(LayerShellState.NO_PLUGIN)
        assert report.state is Readiness.INCOMPLETE
        assert not report.statuses[0].met

    @pytest.mark.parametrize("distro", ["debian", "ubuntu", "pop", "raspbian"])
    def test_qt5_only_distros_are_sent_to_build_it(self, distro):
        report = _report(LayerShellState.NO_PLUGIN, distro=distro)
        assert "Build" in report.steps[0].step.title

    def test_fedora_installs_with_dnf(self):
        report = _report(LayerShellState.NO_PLUGIN, distro="fedora")
        assert report.steps[0].step.command == f"sudo dnf install {PACKAGE}"

    def test_arch_installs_with_pacman(self):
        report = _report(LayerShellState.NO_PLUGIN, distro="arch")
        assert report.steps[0].step.command == f"sudo pacman -S {PACKAGE}"

    def test_an_unknown_distro_is_told_what_to_install_not_how(self):
        report = _report(LayerShellState.NO_PLUGIN, distro="void")
        assert report.steps[0].step.command == ""
        assert PACKAGE in report.steps[0].step.instruction

    def test_a_missing_library_is_an_install_not_a_build(self):
        report = _report(LayerShellState.NO_LIBRARY, distro="debian")
        assert "Build" not in report.steps[0].step.title
        assert report.steps[0].step.command == ""

    def test_every_recipe_ends_by_restarting(self):
        for state in (LayerShellState.NO_PLUGIN, LayerShellState.NO_LIBRARY):
            for distro in ("debian", "fedora", "arch", "void"):
                report = _report(state, distro=distro)
                assert "Restart" in report.steps[-1].step.title

    def test_no_step_is_ever_ticked_off_in_this_session(self):
        """Qt bound its shell integration at startup, so the goal cannot be
        reached from here however much the user installs."""
        report = _report(LayerShellState.NO_PLUGIN)
        assert all(not status.done for status in report.steps)


class TestGate:
    def _gate(self, state):
        view = _View()
        gate = SetupGate(
            SetupReadiness(
                LayerShellSurfaces(_Probe(state)),
                _Facts(MachineProfile(arch="x86_64", distro_id="fedora")),
                all_recipes(),
            ),
            view,
        )
        return gate, view

    def test_a_ready_system_never_sees_the_card(self):
        gate, view = self._gate(LayerShellState.READY)
        started = []
        gate.ensure(lambda: started.append(True))
        assert view.reports == []
        assert started == [True]

    def test_the_card_lets_the_session_start_anyway(self):
        """Non-blocking: the interface is scattered, not absent, and holding the
        user at a card that cannot turn green would strand them."""
        gate, view = self._gate(LayerShellState.NO_PLUGIN)
        started = []
        gate.ensure(lambda: started.append(True))
        assert view.reports and started == []

        view.on_abort()
        assert started == [True]

    def test_the_subject_is_not_blocking(self):
        assert _report(LayerShellState.NO_PLUGIN).subject.blocking is False


class TestRecipeSelection:
    def test_the_source_build_wins_over_the_install_on_debian(self):
        """A Debian-family machine matches both, and installing its Qt 5 package
        would leave it exactly where it started."""
        keys = [recipe.key for recipe in all_recipes()]
        assert keys[0] == "build-layer-shell-qt"

    def test_every_recipe_names_the_trait_it_answers(self):
        traits = {trait for recipe in all_recipes() for trait in recipe.traits}
        assert traits == {NO_PLUGIN, NO_LIBRARY}
