"""Tests for DrmSetupGate — the non-blocking wizard hand-off, over a mocked view."""

from unittest.mock import MagicMock

from domain.drm.gate import DrmSetupGate
from domain.drm.plan import Readiness, ReadinessReport


def _make(state: Readiness, probe=None):
    readiness = MagicMock()
    readiness.report.return_value = ReadinessReport(state)
    view = MagicMock()
    return DrmSetupGate(readiness, view, probe), readiness, view


class TestEnsure:
    def test_ready_system_continues_without_showing_anything(self):
        gate, _, view = _make(Readiness.READY)
        on_done = MagicMock()
        gate.ensure(on_done)
        on_done.assert_called_once_with()
        view.present.assert_not_called()

    def test_incomplete_system_shows_the_checklist(self):
        gate, _, view = _make(Readiness.INCOMPLETE)
        gate.ensure(MagicMock())
        view.present.assert_called_once()

    def test_unsupported_system_shows_the_checklist_too(self):
        gate, _, view = _make(Readiness.UNSUPPORTED)
        gate.ensure(MagicMock())
        view.present.assert_called_once()

    def test_the_view_alone_decides_when_the_session_starts(self):
        gate, _, view = _make(Readiness.INCOMPLETE)
        on_done = MagicMock()
        gate.ensure(on_done)
        on_done.assert_not_called()
        view.present.call_args.kwargs["on_done"]()
        on_done.assert_called_once_with()

    def test_recheck_re_evaluates_the_report(self):
        gate, readiness, view = _make(Readiness.INCOMPLETE)
        gate.ensure(MagicMock())
        assert readiness.report.call_count == 1
        assert view.present.call_args.kwargs["on_recheck"]() is readiness.report()

    def test_verification_is_offered_when_a_probe_is_wired(self):
        probe = MagicMock()
        gate, _, view = _make(Readiness.INCOMPLETE, probe)
        gate.ensure(MagicMock())
        assert view.present.call_args.kwargs["probe"] is probe

    def test_verification_is_absent_without_a_probe(self):
        gate, _, view = _make(Readiness.INCOMPLETE)
        gate.ensure(MagicMock())
        assert view.present.call_args.kwargs["probe"] is None
