"""Tests for the in-game HUD as a setup requirement: what the session's
environment has to carry for every game to be able to show the overlay, what the
card says when it does not, and that it lets the user straight through.

Nothing is read from the real session — the environment is handed in.
"""

from domain.preflight.hud import NO_SESSION_HUD, HudInSession
from domain.preflight.hud_recipes import CONFIG_FILE, all_recipes
from domain.setup.gate import SetupGate
from domain.setup.plan import MachineProfile, Readiness
from domain.setup.readiness import SetupReadiness
from infrastructure.linux.hud.mangohud import MangoHudSession


class _Facts:
    def __init__(self, written: bool = False) -> None:
        self._written = written

    def machine(self) -> MachineProfile:
        return MachineProfile(arch="x86_64", distro_id="fedora")

    def has_command(self, name: str) -> bool:
        return False

    def path_exists(self, pattern: str) -> bool:
        return self._written


class _View:
    def __init__(self) -> None:
        self.reports = []

    def present(self, report, on_recheck, on_done, on_abort, on_remedy, probe=None):
        self.reports.append(report)
        self.on_done = on_done


def _report(environ, written=False):
    return SetupReadiness(
        HudInSession(MangoHudSession(environ)), _Facts(written), all_recipes(),
    ).report()


class TestSessionEnvironment:
    def test_carried_when_the_variable_is_set(self):
        assert MangoHudSession({"MANGOHUD": "1"}).carried_by_session() is True

    def test_not_carried_without_it(self):
        assert MangoHudSession({"PATH": "/usr/bin"}).carried_by_session() is False

    def test_not_carried_when_switched_off(self):
        assert MangoHudSession({"MANGOHUD": "0"}).carried_by_session() is False

    def test_the_kill_switch_wins(self):
        assert MangoHudSession(
            {"MANGOHUD": "1", "DISABLE_MANGOHUD": "1"}).carried_by_session() is False


class TestReadiness:
    def test_a_session_carrying_the_hud_needs_no_card(self):
        assert _report({"MANGOHUD": "1"}).state is Readiness.READY

    def test_a_session_without_it_is_incomplete(self):
        report = _report({})
        assert report.state is Readiness.INCOMPLETE
        assert not report.statuses[0].met

    def test_the_costless_fix_comes_first(self):
        """Handing the whole session to MangoHud loads it into every Vulkan app,
        which has killed applications; letting KD start the launcher costs
        nothing and reaches exactly the games it should."""
        first = _report({}).steps[0].step
        assert first.command == ""
        assert "launcher" in first.title.lower()

    def test_the_session_wide_fix_is_offered_second_with_its_cost(self):
        step = _report({}).steps[-1].step
        assert CONFIG_FILE in step.command
        assert "MANGOHUD=1" in step.command
        assert "every other Vulkan application" in step.instruction

    def test_the_written_file_ticks_its_step_off(self):
        """The file is on disk, but a session's environment is built when it
        starts, so the goal stays out of reach until the next one."""
        report = _report({}, written=True)
        assert report.steps[-1].done is True
        assert report.steps[0].done is False

    def test_the_trait_selects_the_recipe(self):
        assert NO_SESSION_HUD in [t for r in all_recipes() for t in r.traits]


class TestGate:
    def _gate(self, environ):
        view = _View()
        gate = SetupGate(
            SetupReadiness(
                HudInSession(MangoHudSession(environ)), _Facts(), all_recipes()),
            view,
        )
        return gate, view

    def test_a_ready_session_never_sees_the_card(self):
        gate, view = self._gate({"MANGOHUD": "1"})
        reached = []
        gate.ensure(lambda: reached.append(True))
        assert reached == [True]
        assert view.reports == []

    def test_the_card_shows_and_lets_the_user_through(self):
        """Nothing here stops a game from running — only the toggle over one."""
        gate, view = self._gate({})
        reached = []
        gate.ensure(lambda: reached.append(True))
        assert len(view.reports) == 1
        assert reached == []
        view.on_done()
        assert reached == [True]
