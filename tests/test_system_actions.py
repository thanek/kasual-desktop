"""Tests for the system-action registry wiring (ActionDeps / ActionRunner).

Verifies each action drives the right injected port, and that power actions are
gated behind a confirmation while immediate ones are not.
"""

from unittest.mock import MagicMock

import pytest

from domain.system.actions import ActionDeps
from domain.system.runner import ActionRunner
from domain.system.silenced_power import SilencedPowerControl


def _deps():
    return ActionDeps(desktop=MagicMock(), power=MagicMock())


def _auto_confirm(action_key, callback):
    callback()


class TestDispatch:
    def test_hide_desktop_pauses(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("hide_desktop")
        deps.desktop.pause.assert_called_once()

    def test_gamepad_access_opens_the_setup_card(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("gamepad_access")
        deps.desktop.open_gamepad_access_check.assert_called_once()

    def test_sleep_suspends(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("sleep")
        deps.power.suspend.assert_called_once()

    def test_restart_reboots(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("restart")
        deps.power.reboot.assert_called_once()

    def test_shutdown_powers_off(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("shutdown")
        deps.power.poweroff.assert_called_once()


class TestPowerActionsSilenceCuesFirst:
    @pytest.mark.parametrize("action_key, verb", [
        ("sleep", "suspend"), ("restart", "reboot"), ("shutdown", "poweroff"),
    ])
    def test_systemctl_runs_only_after_silencing_and_the_deferral(self, action_key, verb):
        calls = MagicMock()
        deferred = []
        power = SilencedPowerControl(
            calls.power, calls.feedback,
            MagicMock(call_later=lambda _delay, callback: deferred.append(callback)))

        ActionRunner(ActionDeps(desktop=MagicMock(), power=power), _auto_confirm).run(action_key)
        silenced_before_deferral = [name for name, _, _ in calls.mock_calls]
        for callback in deferred:
            callback()

        assert silenced_before_deferral == ["feedback.silence"]
        assert [name for name, _, _ in calls.mock_calls] == ["feedback.silence", f"power.{verb}"]


class TestConfirmationGating:
    def test_power_action_requires_confirmation(self, qapp):
        # show_confirm that never calls back → action must not fire.
        deps = _deps()
        asked = []
        ActionRunner(deps, lambda q, cb: asked.append(q)).run("shutdown")
        assert asked                       # confirmation was requested
        deps.power.poweroff.assert_not_called()

    def test_immediate_action_skips_confirmation(self, qapp):
        deps = _deps()
        asked = []
        ActionRunner(deps, lambda q, cb: asked.append(q)).run("hide_desktop")
        assert asked == []                 # no confirmation for an immediate action
        deps.desktop.pause.assert_called_once()


class TestActionDeps:
    def test_holds_injected_ports(self):
        desktop, power = MagicMock(), MagicMock()
        deps = ActionDeps(desktop=desktop, power=power)
        assert deps.desktop is desktop and deps.power is power


class TestCatalogConsistency:
    """The confirmation *policy* and the confirmation *question text* are two
    facets of the same fact on each action — keep them in lock-step:
    confirmable ⟺ has a question."""

    def test_confirmation_policy_matches_question(self):
        from domain.system.actions import ACTIONS
        for key, action in ACTIONS.items():
            has_question = action.confirm_question is not None
            assert action.needs_confirmation == has_question, key
