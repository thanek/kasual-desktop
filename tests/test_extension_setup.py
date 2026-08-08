"""Tests for the GNOME helper extension as a setup requirement: what the probe
reads out of a silent bus, which way out each state is sent down, and how the
card behaves for a requirement Kasual Desktop cannot run without.

The bus ping, the `gnome-extensions` CLI and the extension directories are all
stubbed; no GNOME Shell is contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from domain.preflight.extension import (
    ABSENT, DISABLED, ENABLE, LOG_OUT, UNLOADED, ExtensionState, HelperExtension,
)
from domain.preflight.extension_recipes import all_recipes
from domain.setup.gate import SetupGate
from domain.setup.plan import MachineProfile, Readiness
from domain.setup.readiness import SetupReadiness
from infrastructure.gnome.extension import GnomeExtensionProbe

_EXT = "infrastructure.gnome.extension"
_UUID = "kasual-helper@consoledesktop.org"


class _Result:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def _probe_state(*, ping, cli, on_disk):
    """State of a probe seeing the given bus/CLI/disk facts."""
    with patch(f"{_EXT}.helper_present", return_value=ping), \
            patch(f"{_EXT}._run", return_value=cli), \
            patch("pathlib.Path.is_file", return_value=on_disk):
        return GnomeExtensionProbe().state()


class _Probe:
    def __init__(self, *states):
        self._states = list(states)

    def state(self):
        return self._states[0] if len(self._states) == 1 else self._states.pop(0)


class _Facts:
    def machine(self):
        return MachineProfile(arch="x86_64", distro_id="fedora")

    def has_command(self, name):
        return False

    def path_exists(self, pattern):
        return False


def _readiness(*states):
    return SetupReadiness(
        HelperExtension(_Probe(*states)), _Facts(), all_recipes(_UUID))


class TestProbeState:
    def test_ready_when_answering(self):
        assert _probe_state(ping=True, cli=None, on_disk=False) is ExtensionState.READY

    def test_disabled_when_shell_knows_it(self):
        assert _probe_state(
            ping=False, cli=_Result(0), on_disk=True) is ExtensionState.DISABLED

    def test_absent_when_nowhere(self):
        assert _probe_state(
            ping=False, cli=_Result(2), on_disk=False) is ExtensionState.ABSENT

    def test_unloaded_when_on_disk_but_shell_never_saw_it(self):
        """Installed into a live session: the files are there, but the Shell built
        its extension list at login, so `gnome-extensions enable` cannot find it."""
        assert _probe_state(
            ping=False, cli=_Result(2), on_disk=True) is ExtensionState.UNLOADED

    def test_disabled_when_cli_unavailable(self):
        assert _probe_state(
            ping=False, cli=None, on_disk=True) is ExtensionState.DISABLED


class TestRequirement:
    @pytest.mark.parametrize(
        "state,trait",
        [(ExtensionState.DISABLED, DISABLED),
         (ExtensionState.ABSENT, ABSENT),
         (ExtensionState.UNLOADED, UNLOADED)],
    )
    def test_each_state_carries_its_own_trait(self, state, trait):
        assert HelperExtension(_Probe(state)).assess().traits == (trait,)

    def test_ready_carries_none(self):
        assessment = HelperExtension(_Probe(ExtensionState.READY)).assess()
        assert assessment.traits == () and assessment.met

    def test_the_shell_is_probed_once_per_report(self):
        """Each probe is a subprocess with a two-second timeout, on the startup
        path."""
        calls = []

        class _Counting:
            def state(self):
                calls.append(True)
                return ExtensionState.DISABLED

        SetupReadiness(
            HelperExtension(_Counting()), _Facts(), all_recipes(_UUID)).report()
        assert len(calls) == 1

    def test_it_is_a_requirement_with_no_way_past_it(self):
        assert HelperExtension(_Probe(ExtensionState.READY)).subject().blocking


class TestRecipeChosen:
    def _report(self, state):
        return _readiness(state).report()

    def test_unresolvable_states_reach_the_user_as_themselves(self):
        """UNLOADED needs a re-login, not the enable command ABSENT advertises."""
        absent = self._report(ExtensionState.ABSENT)
        unloaded = self._report(ExtensionState.UNLOADED)
        assert absent.steps[0].step.title != unloaded.steps[0].step.title

    def test_disabled_offers_to_enable_it_for_you(self):
        report = self._report(ExtensionState.DISABLED)
        assert [r.key for r in report.remedies] == [ENABLE]

    def test_unloaded_offers_the_fresh_session_it_needs(self):
        report = self._report(ExtensionState.UNLOADED)
        assert [r.key for r in report.remedies] == [LOG_OUT]

    def test_absent_offers_nothing_kasual_desktop_can_do(self):
        """The files aren't there — no button reaches that."""
        assert self._report(ExtensionState.ABSENT).remedies == ()

    def test_every_state_names_the_enable_command(self):
        for state in (ExtensionState.DISABLED, ExtensionState.ABSENT,
                      ExtensionState.UNLOADED):
            commands = [s.step.command for s in self._report(state).steps]
            assert f"gnome-extensions enable {_UUID}" in commands

    def test_a_ready_shell_is_ready(self):
        assert self._report(ExtensionState.READY).state is Readiness.READY


class TestGateRouting:
    def test_ready_passes_straight_through(self):
        view = MagicMock()
        done = []
        SetupGate(_readiness(ExtensionState.READY), view).ensure(
            lambda: done.append(True))
        assert done == [True] and not view.present.called

    def test_quitting_is_what_the_last_button_does(self):
        view = MagicMock()
        went = []
        SetupGate(
            _readiness(ExtensionState.ABSENT), view, on_abort=lambda: went.append("quit")
        ).ensure(lambda: went.append("start"))
        view.present.call_args.kwargs["on_abort"]()
        assert went == ["quit"]

    def test_a_remedy_reaches_the_activator(self):
        view = MagicMock()
        activator = MagicMock(enable=MagicMock(return_value=True))
        gate = SetupGate(
            _readiness(ExtensionState.DISABLED), view,
            remedies={ENABLE: activator.enable},
            on_abort=lambda: None,
        )
        gate.ensure(lambda: None)
        report = view.present.call_args.args[0]
        view.present.call_args.kwargs["on_remedy"](report.remedies[0])
        assert activator.enable.call_count == 1


class TestCard:
    """The blocking card: what its buttons say, and when it gets out of the way."""

    def _view(self, mock_gamepad):
        from infrastructure.common.qt.overlays.setup_overlay import QtSetupView
        return QtSetupView(mock_gamepad, MagicMock())

    def _labels(self, dialog):
        return [b.text() for b in dialog._buttons]

    def _present(self, mock_gamepad, probe, *, on_done=None, **kwargs):
        view = self._view(mock_gamepad)
        readiness = SetupReadiness(
            HelperExtension(probe), _Facts(), all_recipes(_UUID))
        kwargs.setdefault("on_abort", lambda: None)
        SetupGate(readiness, view, **kwargs).ensure(
            on_done or (lambda: None), force=True)
        return view.current

    def test_a_blocking_card_offers_to_quit_not_to_continue(self, mock_gamepad):
        card = self._present(mock_gamepad, _Probe(ExtensionState.ABSENT))
        assert self._labels(card) == ["Check again", "Quit"]

    def test_a_remedy_becomes_a_button_of_its_own(self, mock_gamepad):
        card = self._present(mock_gamepad, _Probe(ExtensionState.UNLOADED))
        assert self._labels(card) == ["Log out", "Check again", "Quit"]

    def test_the_card_leaves_as_soon_as_the_blocker_clears(self, mock_gamepad):
        """Nothing is left to read once it is met, and startup is waiting."""
        done = []
        probe = _Probe(ExtensionState.DISABLED, ExtensionState.READY)
        view = self._view(mock_gamepad)
        SetupGate(
            SetupReadiness(HelperExtension(probe), _Facts(), all_recipes(_UUID)),
            view,
            on_abort=lambda: None,
        ).ensure(lambda: done.append(True))
        card = view.current
        card._run_checks()
        assert done == [True] and card._closed

    def test_enabling_it_is_followed_by_a_fresh_look(self, mock_gamepad):
        """The button is only worth having if the card notices it worked."""
        done = []
        probe = _Probe(ExtensionState.DISABLED, ExtensionState.READY)
        view = self._view(mock_gamepad)
        SetupGate(
            SetupReadiness(HelperExtension(probe), _Facts(), all_recipes(_UUID)),
            view,
            remedies={ENABLE: lambda: None},
            on_abort=lambda: None,
        ).ensure(lambda: done.append(True))
        card = view.current
        card._activate(0)
        assert done == [True]

    def test_escape_quits_rather_than_starting_a_session_that_cannot_work(
        self, mock_gamepad
    ):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent
        went = []
        card = self._present(
            mock_gamepad, _Probe(ExtensionState.ABSENT),
            on_abort=lambda: went.append("quit"),
        )
        card.keyPressEvent(
            QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                      Qt.KeyboardModifier.NoModifier))
        assert went == ["quit"]
