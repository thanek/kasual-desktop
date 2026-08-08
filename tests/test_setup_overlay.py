"""Tests for the shared checklist card — the presentation every onboarding
requirement is shown through.

Driven with a stand-in requirement, so what is covered is the card's own
behaviour rather than any one requirement's wording.
"""

from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel

from domain.setup.gate import SetupGate
from domain.setup.plan import (
    GOAL_REACHED, Assessment, MachineProfile, Recipe, Remedy, StatusLine, Step,
    Subject, Verification,
)
from domain.setup.readiness import SetupReadiness
from infrastructure.common.qt.overlays.setup_overlay import QtSetupView

_WORDING = Verification(
    unchecked="not checked yet",
    running="checking…",
    confirmed="it works",
    failed="it does not work",
    detail_unchecked="a short test runs",
    detail_failed="reinstall and try again",
)


class _Facts:
    def machine(self):
        return MachineProfile(arch="x86_64")

    def has_command(self, name):
        return False

    def path_exists(self, pattern):
        return False


class _Requirement:
    def __init__(self, statuses, *, blocking=False, verification=None):
        self._statuses = statuses
        self._blocking = blocking
        self._verification = verification

    def subject(self):
        return Subject(
            title="Something is needed",
            unsupported="No recipe for this system.",
            blocking=self._blocking,
            verification=self._verification,
        )

    def assess(self):
        return Assessment(tuple(self._statuses))

    def satisfied(self, check):
        return False


def _recipe(command="sudo do-it"):
    return Recipe(
        key="only",
        notice="why this is needed",
        steps=(Step(title="Do the thing", instruction="in a terminal",
                    check=GOAL_REACHED, command=command),),
    )


class _Probe:
    def __init__(self):
        self.cancelled = False
        self.on_result = None

    def verify(self, on_result):
        self.on_result = on_result

    def cancel(self):
        self.cancelled = True


def _card(
    mock_gamepad,
    statuses,
    *,
    recipes=None,
    blocking=False,
    verification=None,
    probe=None,
    on_done=None,
    on_abort=None,
    remedies=None,
    force=True,
):
    view = QtSetupView(mock_gamepad, MagicMock())
    readiness = SetupReadiness(
        _Requirement(statuses, blocking=blocking, verification=verification),
        _Facts(),
        (_recipe(),) if recipes is None else recipes,
    )
    needs_a_way_out = blocking and on_abort is None
    SetupGate(
        readiness, view, probe=probe, remedies=remedies,
        on_abort=(lambda: None) if needs_a_way_out else on_abort,
    ).ensure(on_done or (lambda: None), force=force)
    return view.current


def _texts(card, container):
    return [w.text() for w in container.findChildren(QLabel)]


_UNMET = (StatusLine("first thing", met=False, detail="why it matters"),)
_MET = (StatusLine("first thing", met=True, detail="why it matters"),)


class TestStatuses:
    def test_a_met_status_is_ticked(self, mock_gamepad):
        card = _card(mock_gamepad, _MET)
        assert any(t.startswith("✓") for t in _texts(card, card._statuses_container))

    def test_an_unmet_status_is_not(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        assert any(t.startswith("○") for t in _texts(card, card._statuses_container))

    def test_detail_is_for_what_is_still_missing(self, mock_gamepad):
        """A ticked line needs no explanation, and the card is long enough already."""
        card_met = _card(mock_gamepad, _MET)
        card_unmet = _card(mock_gamepad, _UNMET)
        assert "why it matters" not in _texts(card_met, card_met._statuses_container)
        assert "why it matters" in _texts(card_unmet, card_unmet._statuses_container)

    def test_every_status_gets_a_line(self, mock_gamepad):
        statuses = (StatusLine("one", met=True), StatusLine("two", met=False))
        card = _card(mock_gamepad, statuses)
        rendered = " ".join(_texts(card, card._statuses_container))
        assert "one" in rendered and "two" in rendered

    def test_a_recheck_replaces_them_rather_than_stacking(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        before = len(_texts(card, card._statuses_container))
        card._run_checks()
        QApplication.processEvents()
        assert len(_texts(card, card._statuses_container)) == before


class TestSteps:
    def test_steps_are_shown_while_something_is_missing(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        assert "○  1. Do the thing" in _texts(card, card._steps_container)

    def test_a_ready_system_is_spared_the_instructions(self, mock_gamepad):
        card = _card(mock_gamepad, _MET)
        assert not card._steps_area.isVisible()

    def test_the_notice_is_only_for_a_system_that_needs_it(self, mock_gamepad):
        assert _card(mock_gamepad, _UNMET)._notice.text() == "why this is needed"
        assert _card(mock_gamepad, _MET)._notice.text() == ""

    def test_an_unsupported_system_is_told_so_in_the_requirement_s_words(
        self, mock_gamepad
    ):
        card = _card(mock_gamepad, _UNMET, recipes=())
        assert card._guidance.text() == "No recipe for this system."

    def test_only_a_card_you_can_leave_says_come_back_later(self, mock_gamepad):
        passable = _card(mock_gamepad, _UNMET)
        blocking = _card(mock_gamepad, _UNMET, blocking=True)
        assert "come back later" in passable._guidance.text()
        assert "come back later" not in blocking._guidance.text()


class TestCommands:
    def test_the_command_is_offered_verbatim(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        assert "sudo do-it" in _texts(card, card._steps_container)

    def test_copying_puts_it_on_the_clipboard(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        copy = card._steps_container.findChildren(type(card._check_button))[0]
        copy.click()
        assert QApplication.clipboard().text() == "sudo do-it"

    def test_a_step_without_one_gets_no_field(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET, recipes=(_recipe(command=""),))
        assert card._steps_container.findChildren(type(card._check_button)) == []


class TestLeaving:
    def test_a_passable_card_offers_to_continue(self, mock_gamepad):
        card = _card(mock_gamepad, _UNMET)
        assert [b.text() for b in card._buttons] == ["Check again", "Continue"]

    def test_continuing_starts_what_was_waiting(self, mock_gamepad):
        went = []
        card = _card(mock_gamepad, _UNMET, on_done=lambda: went.append("on"))
        card._activate(len(card._buttons) - 1)
        assert went == ["on"]

    def test_escape_continues_rather_than_trapping_the_user(self, mock_gamepad):
        went = []
        card = _card(mock_gamepad, _UNMET, on_done=lambda: went.append("on"))
        card.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                     Qt.KeyboardModifier.NoModifier))
        assert went == ["on"]

    def test_a_passable_card_stays_up_when_a_recheck_clears_it(self, mock_gamepad):
        """The user asked to see this; the tick is the answer they came for."""
        went = []
        card = _card(mock_gamepad, _MET, on_done=lambda: went.append("on"))
        card._run_checks()
        assert went == [] and not card._closed

    def test_the_last_button_is_the_way_out_however_it_is_reached(self, mock_gamepad):
        went = []
        card = _card(mock_gamepad, _UNMET, on_done=lambda: went.append("on"),
                     remedies={"r": lambda: None},
                     recipes=(Recipe(key="k", notice="n", steps=(),
                                     remedies=(Remedy("r", "Fix it"),)),))
        card._handle_pad("cancel")
        assert went == ["on"]


class TestRemedies:
    def _card_with_remedy(self, mock_gamepad, ran):
        recipes = (Recipe(key="k", notice="n",
                          steps=(Step("t", "i", GOAL_REACHED),),
                          remedies=(Remedy("fix", "Fix it"),)),)
        return _card(mock_gamepad, _UNMET, recipes=recipes,
                     remedies={"fix": lambda: ran.append("fix")})

    def test_a_remedy_leads_the_button_row(self, mock_gamepad):
        card = self._card_with_remedy(mock_gamepad, [])
        assert [b.text() for b in card._buttons] == ["Fix it", "Check again", "Continue"]

    def test_pressing_it_runs_the_handler(self, mock_gamepad):
        ran = []
        self._card_with_remedy(mock_gamepad, ran)._activate(0)
        assert ran == ["fix"]


class TestVerification:
    """The seam an asynchronous confirmation plugs into: the parts being in place
    is not the same as the thing working."""

    def test_nothing_is_claimed_without_a_probe(self, mock_gamepad):
        card = _card(mock_gamepad, _MET, verification=_WORDING)
        assert not card._confirmation_status.isVisible()

    def test_nor_without_wording_to_show(self, mock_gamepad):
        card = _card(mock_gamepad, _MET, probe=_Probe())
        assert not card._confirmation_status.isVisible()

    def test_it_starts_out_unchecked(self, mock_gamepad):
        card = _card(mock_gamepad, _MET, probe=_Probe(), verification=_WORDING)
        assert "not checked yet" in card._confirmation_status.text()

    def test_checking_runs_the_probe_and_says_so(self, mock_gamepad):
        probe = _Probe()
        card = _card(mock_gamepad, _MET, probe=probe, verification=_WORDING)
        card._run_checks()
        assert probe.on_result is not None
        assert "checking" in card._confirmation_status.text()
        assert not card._check_button.isEnabled()

    def test_a_confirmed_result_ticks_it(self, mock_gamepad):
        probe = _Probe()
        card = _card(mock_gamepad, _MET, probe=probe, verification=_WORDING)
        card._run_checks()
        probe.on_result(True)
        assert card._confirmation_status.text().startswith("✓")
        assert card._check_button.isEnabled()

    def test_a_failure_explains_itself(self, mock_gamepad):
        probe = _Probe()
        card = _card(mock_gamepad, _MET, probe=probe, verification=_WORDING)
        card._run_checks()
        probe.on_result(False)
        assert card._confirmation_detail.text() == "reinstall and try again"

    def test_leaving_drops_a_check_still_in_flight(self, mock_gamepad):
        probe = _Probe()
        card = _card(mock_gamepad, _MET, probe=probe, verification=_WORDING)
        card._run_checks()
        card._activate(len(card._buttons) - 1)
        assert probe.cancelled

    def test_a_result_after_the_card_closed_is_ignored(self, mock_gamepad):
        probe = _Probe()
        card = _card(mock_gamepad, _MET, probe=probe, verification=_WORDING)
        card._run_checks()
        card._activate(len(card._buttons) - 1)
        probe.on_result(True)


class TestLayout:
    def test_long_text_is_not_clipped(self, mock_gamepad):
        """A word-wrapped QLabel gets no height-for-width from its layout, and
        translations run well past the English they were sized by."""
        statuses = (StatusLine("x" * 20, met=False, detail="word " * 120),)
        card = _card(mock_gamepad, statuses)
        detail = card._statuses_container.findChildren(QLabel)[-1]
        assert detail.heightForWidth(detail.width()) <= detail.height()
