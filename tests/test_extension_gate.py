"""Tests for the GNOME helper extension preflight: what the probe reads out of a
silent bus, and how the gate routes each state.

The bus ping, the `gnome-extensions` CLI and the extension directories are all
stubbed; no GNOME Shell is contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from domain.preflight.extension_gate import ExtensionGate, ExtensionState
from infrastructure.gnome.extension import GnomeExtensionProbe

_EXT = "infrastructure.gnome.extension"


class _Result:
    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def _probe(*, ping, cli, on_disk):
    """State of a probe seeing the given bus/CLI/disk facts."""
    with patch(f"{_EXT}.helper_present", return_value=ping), \
            patch(f"{_EXT}._run", return_value=cli), \
            patch("pathlib.Path.is_file", return_value=on_disk):
        return GnomeExtensionProbe().state()


class TestProbeState:
    def test_ready_when_answering(self):
        assert _probe(ping=True, cli=None, on_disk=False) is ExtensionState.READY

    def test_disabled_when_shell_knows_it(self):
        assert _probe(ping=False, cli=_Result(0), on_disk=True) is ExtensionState.DISABLED

    def test_absent_when_nowhere(self):
        assert _probe(ping=False, cli=_Result(2), on_disk=False) is ExtensionState.ABSENT

    def test_unloaded_when_on_disk_but_shell_never_saw_it(self):
        """Installed into a live session: the files are there, but the Shell built
        its extension list at login, so `gnome-extensions enable` cannot find it."""
        assert _probe(ping=False, cli=_Result(2), on_disk=True) is ExtensionState.UNLOADED

    def test_disabled_when_cli_unavailable(self):
        assert _probe(ping=False, cli=None, on_disk=True) is ExtensionState.DISABLED


class _View:
    def __init__(self):
        self.asked = False
        self.instructed = None
        self.logout = None

    def ask_enable(self, on_accept, on_decline):
        self.asked = True
        self.accept, self.decline = on_accept, on_decline

    def show_instructions(self, state, on_retry, on_quit, on_logout=None):
        self.instructed = state
        self.retry = on_retry
        self.logout = on_logout


class _Probe:
    def __init__(self, *states):
        self._states = list(states)

    def state(self):
        return self._states.pop(0)


class _Activator:
    def __init__(self, result=True):
        self._result = result
        self.calls = 0

    def enable(self):
        self.calls += 1
        return self._result


class _Session:
    def __init__(self):
        self.calls = 0

    def log_out(self):
        self.calls += 1


def _gate(probe, activator=None, view=None, session=None):
    view = view or _View()
    ready = []
    gate = ExtensionGate(probe, activator or _Activator(), view,
                         on_quit=lambda: None, session=session)
    gate.ensure(lambda: ready.append(True))
    return gate, view, ready


class TestGateRouting:
    def test_ready_passes_straight_through(self):
        _, view, ready = _gate(_Probe(ExtensionState.READY))
        assert ready == [True] and not view.asked and view.instructed is None

    def test_disabled_offers_to_enable(self):
        _, view, _ = _gate(_Probe(ExtensionState.DISABLED))
        assert view.asked

    @pytest.mark.parametrize("state",
                             [ExtensionState.ABSENT, ExtensionState.UNLOADED])
    def test_unresolvable_states_instruct_without_offering(self, state):
        """UNLOADED must reach the user as itself — its remedy is a re-login, not
        the enable command ABSENT advertises."""
        _, view, _ = _gate(_Probe(state))
        assert view.instructed is state and not view.asked

    def test_enable_failure_falls_back_to_instructions(self):
        activator = _Activator(result=False)
        _, view, ready = _gate(_Probe(ExtensionState.DISABLED), activator)
        view.accept()
        assert activator.calls == 1
        assert view.instructed is ExtensionState.DISABLED and ready == []

    def test_retry_reprobes(self):
        probe = _Probe(ExtensionState.UNLOADED, ExtensionState.READY)
        _, view, ready = _gate(probe)
        view.retry()
        assert ready == [True]


class TestLogoutRemedy:
    def test_offered_when_a_fresh_session_would_fix_it(self):
        session = _Session()
        _, view, _ = _gate(_Probe(ExtensionState.UNLOADED), session=session)
        view.logout()
        assert session.calls == 1

    def test_withheld_when_relogin_would_not_help(self):
        """ABSENT means the files aren't there — a new session finds nothing either."""
        _, view, _ = _gate(_Probe(ExtensionState.ABSENT), session=_Session())
        assert view.logout is None

    def test_withheld_without_a_session_port(self):
        _, view, _ = _gate(_Probe(ExtensionState.UNLOADED))
        assert view.logout is None


class TestDialogChoices:
    """The dialog grew from a fixed primary/secondary pair to an N-button row;
    the last button stays the way out, for Cancel as well as for a click."""

    def _view(self, mock_gamepad):
        from infrastructure.common.qt.overlays.preflight_overlay import QtPreflightView
        return QtPreflightView(mock_gamepad, MagicMock())

    def _labels(self, dialog):
        return [b.text() for b in dialog._buttons]

    def test_unloaded_offers_logout_instead_of_retry(self, mock_gamepad):
        """Retrying cannot succeed before the session restarts, so it is dropped."""
        view = self._view(mock_gamepad)
        view.show_instructions(ExtensionState.UNLOADED, lambda: None, lambda: None,
                               on_logout=lambda: None)
        assert self._labels(view._current) == ["Log out", "Quit"]

    def test_other_states_keep_two_choices(self, mock_gamepad):
        view = self._view(mock_gamepad)
        view.show_instructions(ExtensionState.ABSENT, lambda: None, lambda: None)
        assert self._labels(view._current) == ["Retry", "Quit"]

    def test_logout_button_runs_logout_not_quit(self, mock_gamepad):
        view = self._view(mock_gamepad)
        done = []
        view.show_instructions(ExtensionState.UNLOADED, lambda: done.append("retry"),
                               lambda: done.append("quit"),
                               on_logout=lambda: done.append("logout"))
        view._current._activate(0)
        assert done == ["logout"]

    def test_cancel_resolves_to_the_last_choice(self, mock_gamepad):
        view = self._view(mock_gamepad)
        done = []
        view.ask_enable(lambda: done.append("enable"), lambda: done.append("decline"))
        view._current._handle_pad("cancel")
        assert done == ["decline"]

    def test_message_is_not_clipped(self, mock_gamepad):
        """A word-wrapped QLabel gets no height-for-width from its layout; the
        longer translations were being cut off mid-paragraph."""
        from PyQt6.QtWidgets import QLabel
        view = self._view(mock_gamepad)
        view.show_instructions(ExtensionState.UNLOADED, lambda: None, lambda: None,
                               on_logout=lambda: None)
        label = view._current.findChild(QLabel)
        assert label.heightForWidth(label.width()) <= label.height()

    def test_install_hint_fits_on_one_line(self, mock_gamepad):
        from PyQt6.QtGui import QFontMetrics
        from PyQt6.QtWidgets import QLabel
        from infrastructure.common.qt.overlays.preflight_overlay import _INSTALL_HINT
        view = self._view(mock_gamepad)
        view.show_instructions(ExtensionState.ABSENT, lambda: None, lambda: None)
        label = view._current.findChild(QLabel)
        assert QFontMetrics(label.font()).horizontalAdvance(_INSTALL_HINT) <= label.width()
