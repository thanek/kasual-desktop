"""Tests for the shared onboarding core: how a recipe is chosen, how its steps
are evaluated against a live system, and how the gate routes the result.

Nothing here names a concrete requirement — the point of the core is that the
requirement is a parameter.
"""

import pytest

from domain.setup.gate import SetupGate
from domain.setup.plan import (
    COMMAND, GOAL_REACHED, PATH, Assessment, Check, MachineProfile, Readiness,
    Recipe, Remedy, StatusLine, Step, Subject, recipe_for,
)
from domain.setup.readiness import SetupReadiness

CUSTOM = Check("custom", "own")


def _step(check=GOAL_REACHED, title="do it"):
    return Step(title=title, instruction="how", check=check)


def _recipe(key="only", steps=(), **kwargs):
    return Recipe(key=key, notice="why", steps=steps or (_step(),), **kwargs)


class _Facts:
    def __init__(self, machine=None, commands=(), paths=()):
        self._machine = machine or MachineProfile(arch="x86_64")
        self._commands = set(commands)
        self._paths = set(paths)

    def machine(self):
        return self._machine

    def has_command(self, name):
        return name in self._commands

    def path_exists(self, pattern):
        return pattern in self._paths


class _Requirement:
    def __init__(self, *, met=True, traits=(), custom=False, blocking=False):
        self._met = met
        self._traits = traits
        self._custom = custom
        self._blocking = blocking
        self.passes = 0

    def subject(self):
        return Subject(title="T", unsupported="U", blocking=self._blocking)

    def assess(self):
        self.passes += 1
        return Assessment((StatusLine("only", met=self._met),), self._traits)

    def satisfied(self, check):
        return self._custom

    def resolve(self):
        self._met = True


class _View:
    def __init__(self):
        self.report = None

    def present(self, report, on_recheck, on_done, on_abort, on_remedy, probe=None):
        self.report = report
        self.recheck = on_recheck
        self.done = on_done
        self.abort = on_abort
        self.remedy = on_remedy
        self.probe = probe


class TestRecipeSelection:
    def test_first_match_wins(self):
        specific = _recipe(key="specific", arch=("aarch64",))
        catch_all = _recipe(key="catch-all")
        machine = MachineProfile(arch="aarch64")
        assert recipe_for(machine, (specific, catch_all)).key == "specific"

    def test_empty_fields_match_any_machine(self):
        machine = MachineProfile(arch="riscv64", distro_id="nixos")
        assert recipe_for(machine, (_recipe(),)).key == "only"

    def test_a_recipe_needs_every_trait_it_names(self):
        recipe = _recipe(traits=("ostree", "raspberrypi"))
        half = MachineProfile(arch="aarch64", traits=("ostree",))
        both = MachineProfile(arch="aarch64", traits=("ostree", "raspberrypi"))
        assert recipe_for(half, (recipe,)) is None
        assert recipe_for(both, (recipe,)) is recipe

    def test_id_like_counts_as_the_distro(self):
        """Pop!_OS reports `ubuntu debian`, so a Debian recipe already covers it."""
        recipe = _recipe(distros=("debian",))
        machine = MachineProfile(arch="x86_64", distro_id="pop", like=("ubuntu", "debian"))
        assert recipe_for(machine, (recipe,)) is recipe

    def test_no_match_leaves_the_choice_open(self):
        machine = MachineProfile(arch="x86_64")
        assert recipe_for(machine, (_recipe(arch=("aarch64",)),)) is None


class TestReadinessReport:
    def test_traits_the_requirement_found_select_the_recipe(self):
        """What the probe saw is what picks the way out of it — the machine alone
        cannot tell which state a requirement is in."""
        matching = _recipe(key="for-state", traits=("state-x",))
        readiness = SetupReadiness(
            _Requirement(met=False, traits=("state-x",)),
            _Facts(),
            (matching, _recipe(key="catch-all")),
        )
        assert readiness.report().steps[0].step.title == "do it"
        assert readiness.report().state is Readiness.INCOMPLETE

    def test_unmet_without_a_recipe_is_unsupported(self):
        readiness = SetupReadiness(
            _Requirement(met=False), _Facts(), (_recipe(arch=("aarch64",)),))
        assert readiness.report().state is Readiness.UNSUPPORTED

    def test_met_without_a_recipe_is_still_ready(self):
        readiness = SetupReadiness(_Requirement(met=True), _Facts(), ())
        assert readiness.report().state is Readiness.READY

    def test_a_met_requirement_reports_ready_with_steps_still_unticked(self):
        """Readiness is the requirement itself, never its prerequisites: someone
        who got there another way is ready with every step unticked."""
        recipe = _recipe(steps=(_step(check=Check(PATH, "/nowhere")),))
        report = SetupReadiness(_Requirement(met=True), _Facts(), (recipe,)).report()
        assert report.state is Readiness.READY
        assert report.remaining == 1

    def test_one_pass_over_the_system_per_report(self):
        """Probing can mean a subprocess with a timeout; the report must not pay
        for it twice."""
        requirement = _Requirement(met=False, traits=())
        SetupReadiness(requirement, _Facts(), (_recipe(),)).report()
        assert requirement.passes == 1


class TestStepChecks:
    def _remaining(self, check, facts, **requirement):
        recipe = _recipe(steps=(_step(check=check),))
        report = SetupReadiness(
            _Requirement(met=False, **requirement), facts, (recipe,)).report()
        return report.remaining

    def test_command_check_reads_the_machine(self):
        assert self._remaining(Check(COMMAND, "udevadm"), _Facts()) == 1
        assert self._remaining(
            Check(COMMAND, "udevadm"), _Facts(commands=("udevadm",))) == 0

    def test_path_check_reads_the_machine(self):
        assert self._remaining(Check(PATH, "/etc/x"), _Facts(paths=("/etc/x",))) == 0

    def test_goal_check_follows_the_requirement_itself(self):
        recipe = _recipe(steps=(_step(check=GOAL_REACHED),))
        met = SetupReadiness(_Requirement(met=True), _Facts(), (recipe,)).report()
        assert met.remaining == 0

    def test_an_unknown_kind_is_the_requirement_s_own_to_answer(self):
        assert self._remaining(CUSTOM, _Facts(), custom=True) == 0
        assert self._remaining(CUSTOM, _Facts(), custom=False) == 1


class TestGate:
    def test_ready_passes_straight_through(self):
        view = _View()
        done = []
        SetupGate(SetupReadiness(_Requirement(met=True), _Facts(), ()),
                  view).ensure(lambda: done.append(True))
        assert done == [True] and view.report is None

    def test_unmet_presents_the_card_and_withholds_nothing_yet(self):
        view = _View()
        done = []
        SetupGate(SetupReadiness(_Requirement(met=False), _Facts(), (_recipe(),)),
                  view).ensure(lambda: done.append(True))
        assert view.report.state is Readiness.INCOMPLETE and done == []

    def test_force_shows_the_card_on_a_ready_system(self):
        """Reopening it deliberately: the confirmation is what the user came for."""
        view = _View()
        SetupGate(SetupReadiness(_Requirement(met=True), _Facts(), ()),
                  view).ensure(lambda: None, force=True)
        assert view.report.state is Readiness.READY

    def test_rechecking_reruns_the_assessment(self):
        view = _View()
        requirement = _Requirement(met=False)
        SetupGate(SetupReadiness(requirement, _Facts(), (_recipe(),)),
                  view).ensure(lambda: None)
        requirement.resolve()
        assert view.recheck().state is Readiness.READY

    def test_a_remedy_runs_the_handler_registered_for_its_key(self):
        view = _View()
        ran = []
        SetupGate(
            SetupReadiness(_Requirement(met=False), _Facts(), (_recipe(),)),
            view,
            remedies={"enable": lambda: ran.append("enable")},
        ).ensure(lambda: None)
        view.remedy(Remedy("enable", "Enable"))
        assert ran == ["enable"]

    def test_an_unhandled_remedy_key_is_ignored(self):
        view = _View()
        SetupGate(SetupReadiness(_Requirement(met=False), _Facts(), (_recipe(),)),
                  view).ensure(lambda: None)
        view.remedy(Remedy("nothing-here", "?"))

    def test_a_blocking_gate_leads_out_through_abort(self):
        view = _View()
        went = []
        SetupGate(
            SetupReadiness(_Requirement(met=False, blocking=True), _Facts(),
                           (_recipe(),)),
            view,
            on_abort=lambda: went.append("abort"),
        ).ensure(lambda: went.append("done"))
        view.abort()
        assert went == ["abort"]

    def test_a_passable_gate_needs_no_abort(self):
        view = _View()
        went = []
        SetupGate(
            SetupReadiness(_Requirement(met=False), _Facts(), (_recipe(),)),
            view,
        ).ensure(lambda: went.append("done"))
        view.abort()
        assert went == ["done"]

    def test_a_blocking_gate_without_an_abort_is_a_wiring_error(self):
        """Its way out is labelled Quit; falling back to on_done would start the
        very session the requirement exists to prevent."""
        gate = SetupGate(
            SetupReadiness(_Requirement(met=False, blocking=True), _Facts(),
                           (_recipe(),)),
            _View(),
        )
        with pytest.raises(ValueError):
            gate.ensure(lambda: None)

    def test_a_blocking_gate_that_is_met_never_gets_that_far(self):
        """Nothing is presented, so nothing needs a way out of it."""
        done = []
        SetupGate(
            SetupReadiness(_Requirement(met=True, blocking=True), _Facts(), ()),
            _View(),
        ).ensure(lambda: done.append(True))
        assert done == [True]
