"""Tests for the DRM setup overlay — the two-condition card, offscreen."""

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from domain.drm.plan import (
    Check, CheckKind, Readiness, ReadinessReport, Step, StepStatus,
)
from infrastructure.common.qt.overlays.drm_setup_overlay import _DrmSetupDialog
from infrastructure.common.qt.ui import styles

_INSTALL = Step("Install", "Install it", Check(CheckKind.COMMAND, "widevine-installer"),
                command="dnf install widevine-installer")
_RUN = Step("Run", "Run it", Check(CheckKind.CDM), command="widevine-installer")


def _report(state=Readiness.INCOMPLETE, done=(False, False)):
    steps = tuple(
        StepStatus(step, is_done)
        for step, is_done in zip((_INSTALL, _RUN), done)
    )
    return ReadinessReport(state, steps, notice="Notice")


def _make(mock_gamepad, report=None, on_recheck=None, on_done=None, on_verify=None):
    report = report or _report()
    return _DrmSetupDialog(
        report,
        on_recheck or (lambda: report),
        on_done or (lambda: None),
        on_verify,
        mock_gamepad,
        MagicMock(),
    )


def _is_met(label: QLabel) -> bool:
    return (label.text().startswith("✓")
            and "bold" in label.styleSheet()
            and styles.COLOR_RUNNING in label.styleSheet())


def _copy_buttons(dialog) -> list[QPushButton]:
    return [
        button
        for i in range(dialog._steps_layout.count())
        for button in dialog._steps_layout.itemAt(i).widget().findChildren(QPushButton)
    ]


class TestModuleCondition:
    def test_missing_module_shows_the_steps_that_install_it(self, mock_gamepad):
        dialog = _make(mock_gamepad)
        assert not _is_met(dialog._status_module)
        assert dialog._steps_layout.count() == 2
        assert dialog._module_detail.isVisible()

    def test_installed_module_is_ticked_and_drops_the_instructions(self, mock_gamepad):
        dialog = _make(mock_gamepad, _report(Readiness.READY, (True, True)))
        assert _is_met(dialog._status_module)
        assert dialog._steps_layout.count() == 0
        assert not dialog._module_detail.isVisible()

    def test_unsupported_system_says_so_instead_of_listing_steps(self, mock_gamepad):
        dialog = _make(mock_gamepad, ReadinessReport(Readiness.UNSUPPORTED))
        assert not _is_met(dialog._status_module)
        assert dialog._steps_layout.count() == 0
        assert "no Widevine recipe" in dialog._module_detail.text()

    def test_notice_is_shown_only_while_the_module_is_missing(self, mock_gamepad):
        assert _make(mock_gamepad)._notice.text() == "Notice"
        installed = _make(mock_gamepad, _report(Readiness.READY, (True, True)))
        assert not installed._notice.isVisible()

    def test_marks_completed_steps_apart_from_pending_ones(self, mock_gamepad):
        dialog = _make(mock_gamepad, _report(done=(True, False)))
        first, second = (dialog._steps_layout.itemAt(i).widget() for i in range(2))
        assert first.findChildren(QLabel)[0].text().startswith("✓")
        assert second.findChildren(QLabel)[0].text().startswith("○")


class TestPlaybackCondition:
    def test_starts_unchecked_rather_than_claiming_either_outcome(self, mock_gamepad):
        dialog = _make(mock_gamepad, on_verify=lambda: True)
        assert not _is_met(dialog._status_playback)
        assert "not been checked" in dialog._status_playback.text()

    def test_confirmed_playback_is_ticked(self, mock_gamepad):
        dialog = _make(mock_gamepad, _report(Readiness.READY, (True, True)),
                       on_verify=lambda: True)
        dialog._perform_checks()
        assert _is_met(dialog._status_playback)
        assert "plays" in dialog._status_playback.text()

    def test_failed_playback_explains_the_likely_cause(self, mock_gamepad):
        dialog = _make(mock_gamepad, _report(Readiness.READY, (True, True)),
                       on_verify=lambda: False)
        dialog._perform_checks()
        assert not _is_met(dialog._status_playback)
        assert "did not load" in dialog._playback_detail.text()

    def test_failure_without_the_module_does_not_claim_it_is_installed(
        self, mock_gamepad
    ):
        dialog = _make(mock_gamepad, on_verify=lambda: False)
        dialog._perform_checks()
        assert "is installed but" not in dialog._playback_detail.text()
        assert "until Widevine is installed" in dialog._playback_detail.text()

    def test_hidden_when_no_probe_is_wired(self, mock_gamepad):
        dialog = _make(mock_gamepad)
        assert not dialog._status_playback.isVisible()


class TestChecking:
    def test_one_button_runs_both_conditions_in_order(self, mock_gamepad):
        calls = []
        report = _report(Readiness.READY, (True, True))

        def recheck():
            calls.append("recheck")
            return report

        def verify():
            calls.append("verify")
            return True

        dialog = _make(mock_gamepad, on_recheck=recheck, on_verify=verify)
        dialog._perform_checks()
        assert calls == ["recheck", "verify"]
        assert _is_met(dialog._status_module)
        assert _is_met(dialog._status_playback)

    def test_checking_runs_even_when_the_module_is_still_missing(self, mock_gamepad):
        verify = MagicMock(return_value=False)
        dialog = _make(mock_gamepad, on_verify=verify)
        dialog._perform_checks()
        verify.assert_called_once_with()

    def test_instructions_survive_a_check_that_changes_nothing(self, mock_gamepad):
        dialog = _make(mock_gamepad, on_verify=lambda: False)
        dialog.show()
        for _ in range(3):
            dialog._perform_checks()
        assert dialog._steps_layout.count() == 2
        assert dialog._steps_area.isVisible()
        assert dialog._steps_area.maximumHeight() > 0

    def test_a_later_check_can_withdraw_an_earlier_confirmation(self, mock_gamepad):
        outcomes = iter([True, False])
        dialog = _make(mock_gamepad, _report(Readiness.READY, (True, True)),
                       on_verify=lambda: next(outcomes))
        dialog._perform_checks()
        assert _is_met(dialog._status_playback)
        dialog._perform_checks()
        assert not _is_met(dialog._status_playback)

    def test_the_button_returns_after_the_check(self, mock_gamepad):
        dialog = _make(mock_gamepad, on_verify=lambda: True)
        dialog._perform_checks()
        assert dialog._check_button.isEnabled()

    def test_checking_stays_open_so_the_user_can_keep_working(self, mock_gamepad):
        on_done = MagicMock()
        dialog = _make(mock_gamepad, on_done=on_done, on_verify=lambda: True)
        dialog._perform_checks()
        on_done.assert_not_called()
        assert dialog._handle_pad in mock_gamepad._stack


class TestCopyingCommands:
    def test_every_command_can_be_copied(self, mock_gamepad):
        assert len(_copy_buttons(_make(mock_gamepad))) == 2

    def test_copying_puts_the_command_on_the_clipboard(self, mock_gamepad):
        dialog = _make(mock_gamepad)
        _copy_buttons(dialog)[0].click()
        assert QApplication.clipboard().text() == "dnf install widevine-installer"

    def test_the_control_acknowledges_the_copy(self, mock_gamepad):
        button = _copy_buttons(_make(mock_gamepad))[0]
        assert button.property("copied") is False
        button.click()
        assert button.property("copied") is True

    def test_the_control_is_an_icon_inside_the_command_box(self, mock_gamepad):
        button = _copy_buttons(_make(mock_gamepad))[0]
        assert button.text() == ""
        assert not button.icon().isNull()
        command_box = button.parent()
        assert command_box.findChildren(QLabel)[0].text().startswith("dnf install")


class TestLeaving:
    def test_continue_reports_done_and_deregisters_the_pad(self, mock_gamepad):
        on_done = MagicMock()
        dialog = _make(mock_gamepad, on_done=on_done)
        dialog._finish()
        on_done.assert_called_once_with()
        assert dialog._handle_pad not in mock_gamepad._stack

    def test_cancel_leaves_rather_than_blocking(self, mock_gamepad):
        on_done = MagicMock()
        dialog = _make(mock_gamepad, on_done=on_done)
        dialog._handle_pad("cancel")
        on_done.assert_called_once_with()

    def test_a_stray_click_on_the_backdrop_keeps_the_card_open(self, mock_gamepad):
        on_done = MagicMock()
        dialog = _make(mock_gamepad, on_done=on_done)
        dialog._on_outside_click()
        on_done.assert_not_called()
        assert dialog._handle_pad in mock_gamepad._stack

    def test_leaving_twice_reports_done_once(self, mock_gamepad):
        on_done = MagicMock()
        dialog = _make(mock_gamepad, on_done=on_done)
        dialog._finish()
        dialog._finish()
        on_done.assert_called_once_with()
