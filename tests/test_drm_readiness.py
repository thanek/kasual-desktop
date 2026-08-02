"""Tests for DrmReadiness — the report built from recipes plus a fake system."""

from domain.drm.plan import (
    Check, CheckKind, MachineProfile, Readiness, Recipe, Step,
)
from domain.drm.readiness import DrmReadiness

_MACHINE = MachineProfile(arch="aarch64", distro_id="fedora")


class FakeFacts:
    def __init__(self, *, cdm=None, commands=(), paths=(), machine=_MACHINE):
        self._cdm = cdm
        self._commands = set(commands)
        self._paths = set(paths)
        self._machine = machine

    def machine(self):
        return self._machine

    def has_command(self, name):
        return name in self._commands

    def path_exists(self, pattern):
        return pattern in self._paths

    def cdm_path(self):
        return self._cdm


def _recipe(*steps: Step) -> Recipe:
    return Recipe(key="test", notice="notice", steps=steps, arch=("aarch64",))


_INSTALLER = Step("Install", "…", Check(CheckKind.COMMAND, "widevine-installer"),
                  command="dnf install widevine-installer")
_RUN = Step("Run", "…", Check(CheckKind.CDM), command="widevine-installer")


class TestState:
    def test_ready_when_the_cdm_is_present(self):
        readiness = DrmReadiness(FakeFacts(cdm="/cdm.so"), (_recipe(_RUN),))
        assert readiness.report().state is Readiness.READY

    def test_incomplete_when_a_recipe_matches_but_the_cdm_is_absent(self):
        readiness = DrmReadiness(FakeFacts(), (_recipe(_RUN),))
        assert readiness.report().state is Readiness.INCOMPLETE

    def test_unsupported_when_no_recipe_matches(self):
        facts = FakeFacts(machine=MachineProfile(arch="riscv64"))
        readiness = DrmReadiness(facts, (_recipe(_RUN),))
        assert readiness.report().state is Readiness.UNSUPPORTED

    def test_a_cdm_obtained_elsewhere_beats_an_unsupported_machine(self):
        facts = FakeFacts(cdm="/cdm.so", machine=MachineProfile(arch="riscv64"))
        readiness = DrmReadiness(facts, (_recipe(_RUN),))
        assert readiness.report().state is Readiness.READY

    def test_ready_even_when_the_prerequisite_steps_are_unmet(self):
        readiness = DrmReadiness(FakeFacts(cdm="/cdm.so"), (_recipe(_INSTALLER, _RUN),))
        report = readiness.report()
        assert report.state is Readiness.READY
        assert not report.steps[0].done


class TestSteps:
    def test_reports_each_step_in_recipe_order(self):
        readiness = DrmReadiness(FakeFacts(), (_recipe(_INSTALLER, _RUN),))
        titles = [status.step.title for status in readiness.report().steps]
        assert titles == ["Install", "Run"]

    def test_command_check_follows_the_system(self):
        facts = FakeFacts(commands=("widevine-installer",))
        readiness = DrmReadiness(facts, (_recipe(_INSTALLER, _RUN),))
        report = readiness.report()
        assert report.steps[0].done
        assert not report.steps[1].done

    def test_path_check_follows_the_system(self):
        step = Step("Config", "…", Check(CheckKind.PATH, "/etc/widevine"))
        facts = FakeFacts(paths=("/etc/widevine",))
        readiness = DrmReadiness(facts, (_recipe(step, _RUN),))
        assert readiness.report().steps[0].done

    def test_remaining_counts_the_unticked_steps(self):
        facts = FakeFacts(commands=("widevine-installer",))
        readiness = DrmReadiness(facts, (_recipe(_INSTALLER, _RUN),))
        assert readiness.report().remaining == 1

    def test_unsupported_report_carries_no_steps_or_notice(self):
        facts = FakeFacts(machine=MachineProfile(arch="riscv64"))
        report = DrmReadiness(facts, (_recipe(_RUN),)).report()
        assert report.steps == ()
        assert report.notice == ""

    def test_matched_report_carries_the_recipe_notice(self):
        report = DrmReadiness(FakeFacts(), (_recipe(_RUN),)).report()
        assert report.notice == "notice"
