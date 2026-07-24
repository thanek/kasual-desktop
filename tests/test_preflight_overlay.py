"""Tests that every preflight dialog shows its whole message.

A wrapped QLabel reports a single line's height, so the card was built too short and
silently clipped the text — the GNOME dialogs had been doing it before the
layer-shell one made it obvious.
"""

import pytest

from PyQt6.QtWidgets import QLabel

from domain.preflight.extension_gate import ExtensionState
from infrastructure.common.qt.overlays.preflight_overlay import QtPreflightView


class _Pad:
    def push_handler(self, *_args) -> None: ...
    def pop_handler(self, *_args) -> None: ...


class _Feedback:
    def play(self, *_args) -> None: ...


@pytest.fixture
def view(qapp):
    return QtPreflightView(_Pad(), _Feedback())


def _clipping(view: QtPreflightView) -> int:
    """How many pixels of the message do not fit; 0 when it all shows."""
    label = view._current._card.findChild(QLabel)
    return max(0, label.heightForWidth(label.width()) - label.height())


class TestMessageFits:
    def test_missing_layer_shell(self, view):
        view.show_missing_layer_shell(lambda: None, lambda: None)
        assert _clipping(view) == 0

    @pytest.mark.parametrize("state", [ExtensionState.ABSENT, ExtensionState.DISABLED])
    def test_gnome_instructions(self, view, state):
        view.show_instructions(state, lambda: None, lambda: None)
        assert _clipping(view) == 0

    def test_gnome_enable_prompt(self, view):
        view.ask_enable(lambda: None, lambda: None)
        assert _clipping(view) == 0


class TestLayerShellDialog:
    def test_offers_continuing_and_quitting(self, view):
        view.show_missing_layer_shell(lambda: None, lambda: None)
        dialog = view._current
        assert dialog._btn_secondary.text()
        assert dialog._btn_primary.text()

    def test_continuing_is_the_primary_action(self, view):
        continued, quit_calls = [], []
        view.show_missing_layer_shell(lambda: continued.append(1),
                                      lambda: quit_calls.append(1))
        view._current._activate(0)
        assert (continued, quit_calls) == ([1], [])

    def test_cancelling_quits_rather_than_continuing(self, view):
        # B / Escape reaches the secondary action, as on the GNOME gate.
        continued, quit_calls = [], []
        view.show_missing_layer_shell(lambda: continued.append(1),
                                      lambda: quit_calls.append(1))
        view._current._dismiss_secondary()
        assert (continued, quit_calls) == ([], [1])

    def test_cannot_be_dismissed_by_clicking_outside(self, view):
        continued, quit_calls = [], []
        view.show_missing_layer_shell(lambda: continued.append(1),
                                      lambda: quit_calls.append(1))
        view._current._on_outside_click()
        assert (continued, quit_calls) == ([], [])

    def test_gets_a_wider_card_than_the_gnome_dialogs(self, view):
        view.show_missing_layer_shell(lambda: None, lambda: None)
        wide = view._current._card.width()
        view.ask_enable(lambda: None, lambda: None)
        assert wide > view._current._card.width()
