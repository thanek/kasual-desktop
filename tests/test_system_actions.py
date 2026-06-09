"""Tests for the system-action registry wiring (ActionDeps / ActionRunner).

Verifies each action drives the right injected port, and that power actions are
gated behind a confirmation while immediate ones are not.
"""

from unittest.mock import MagicMock

from application.system_actions import ActionDeps, ActionRunner


def _deps():
    return ActionDeps(desktop=MagicMock(), power=MagicMock())


def _auto_confirm(action_key, callback):
    callback()


class TestDispatch:
    def test_volume_opens_overlay(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("volume")
        deps.desktop.open_volume_overlay.assert_called_once()

    def test_hide_desktop_pauses(self, qapp):
        deps = _deps()
        ActionRunner(deps, _auto_confirm).run("hide_desktop")
        deps.desktop.pause.assert_called_once()

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
        ActionRunner(deps, lambda q, cb: asked.append(q)).run("volume")
        assert asked == []                 # no confirmation for volume
        deps.desktop.open_volume_overlay.assert_called_once()


class TestActionDeps:
    def test_holds_injected_ports(self):
        desktop, power = MagicMock(), MagicMock()
        deps = ActionDeps(desktop=desktop, power=power)
        assert deps.desktop is desktop and deps.power is power


class TestCatalogPresentationConsistency:
    """The confirmation *policy* (application catalog) and the confirmation
    *question text* (view presentation) are two facets of the same fact — keep
    them in lock-step: confirmable ⟺ has a question."""

    def test_confirmation_policy_matches_presentation(self):
        from application.system_actions import ACTIONS
        from infrastructure.qt.ui.action_view import PRESENTATION
        assert PRESENTATION.keys() == ACTIONS.keys()
        for key, action in ACTIONS.items():
            has_question = PRESENTATION[key].confirm_question is not None
            assert action.needs_confirmation == has_question, key
