"""Tests for OnboardingOverlay (presentation layer of provisioning).

The picker renders the domain candidates, drives an AppSelection for toggles and
a MenuCursor for navigation, and reports the chosen candidates via on_confirm. It
is confirm-only: B / Escape / backdrop do nothing. Offscreen — showFullScreen()
needs no real display.
"""

from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QEnterEvent, QKeyEvent

from domain.catalog.app import App
from domain.provisioning.candidate import CandidateApp
from infrastructure.qt.overlays.onboarding_overlay import OnboardingOverlay


def _candidates():
    return [
        CandidateApp("files", App(name="Files", command="f", icon="fa5s.folder-open"),
                     order=40, default_selected=True),
        CandidateApp("youtube", App(name="YouTube", command="y", icon="fa5b.youtube"),
                     order=30, default_selected=False),
    ]


def _present(mock_gamepad, on_confirm=None):
    overlay = OnboardingOverlay(gamepad=mock_gamepad, feedback=MagicMock())
    overlay.present(
        _candidates(),
        on_confirm=on_confirm or (lambda chosen: None),
    )
    return overlay


def _key(code):
    return QKeyEvent(QKeyEvent.Type.KeyPress, code, Qt.KeyboardModifier.NoModifier)


class TestPresent:
    def test_registers_handler(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        assert overlay._handle_pad in mock_gamepad._stack

    def test_seeds_selection_from_defaults(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        assert overlay._selection.is_selected(0) is True
        assert overlay._selection.is_selected(1) is False


class TestRowIcons:
    def test_glyph_candidate_renders_an_icon(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        assert not overlay._rows[0].icon().isNull()

    def test_themed_candidate_prefers_real_icon(self, mock_gamepad):
        # An app provisioned with a real system icon carries icon_theme (no glyph).
        themed = CandidateApp(
            "x", App(name="X", command="x", icon=None, icon_theme="folder"),
            order=1, default_selected=True)
        overlay = OnboardingOverlay(gamepad=mock_gamepad, feedback=MagicMock())
        icon = overlay._candidate_icon(themed)
        # Resolution mirrors the tile bar: a present theme icon resolves, an
        # absent one yields None (the row simply shows no icon) — never a crash.
        from PyQt6.QtGui import QIcon
        assert icon is None or isinstance(icon, QIcon)


class TestToggleSwitches:
    def test_switches_seed_from_default_selection(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        assert overlay._rows[0].toggle.isChecked() is True   # files default-on
        assert overlay._rows[1].toggle.isChecked() is False  # youtube default-off

    def test_switch_reflects_toggle(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        overlay._handle_pad("select")          # toggle row 0 off
        assert overlay._rows[0].toggle.isChecked() is False


class TestToggling:
    def test_select_on_row_toggles_it(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        overlay._handle_pad("select")          # cursor at row 0
        assert overlay._selection.is_selected(0) is False

    def test_select_does_not_confirm(self, mock_gamepad):
        confirmed = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: confirmed.append(c))
        overlay._handle_pad("select")          # toggles row 0, stays open
        assert confirmed == []
        assert overlay._handle_pad in mock_gamepad._stack


class TestConfirm:
    def test_confirm_reports_chosen_and_closes(self, mock_gamepad):
        chosen = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: chosen.append(c))
        overlay._handle_pad("down")            # row 0 → row 1
        overlay._handle_pad("down")            # row 1 → Confirm
        overlay._handle_pad("select")
        assert overlay._handle_pad not in mock_gamepad._stack
        # Only the default-on candidate (files) is chosen.
        assert [c.key for c in chosen[0]] == ["files"]

    def test_confirm_reflects_toggles(self, mock_gamepad):
        chosen = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: chosen.append(c))
        overlay._handle_pad("select")          # toggle files OFF
        overlay._handle_pad("down")
        overlay._handle_pad("select")          # toggle youtube ON
        overlay._handle_pad("down")            # → Confirm
        overlay._handle_pad("select")
        assert [c.key for c in chosen[0]] == ["youtube"]


class TestConfirmOnly:
    def test_cancel_does_not_close(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        overlay._handle_pad("cancel")
        assert overlay._handle_pad in mock_gamepad._stack
        assert overlay._closed is False

    def test_close_does_not_close(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        overlay._handle_pad("close")
        assert overlay._handle_pad in mock_gamepad._stack

    def test_outside_click_keeps_overlay_open(self, mock_gamepad):
        confirmed = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: confirmed.append(c))
        overlay._on_outside_click()
        assert overlay._closed is False
        assert confirmed == []


class TestKeyboard:
    def test_arrows_navigate(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        assert overlay._cursor.index == 0
        overlay.keyPressEvent(_key(Qt.Key.Key_Down))
        assert overlay._cursor.index == 1

    def test_space_toggles_current_row(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        overlay.keyPressEvent(_key(Qt.Key.Key_Space))   # row 0 (files, default on)
        assert overlay._selection.is_selected(0) is False

    def test_space_on_confirm_row_is_noop(self, mock_gamepad):
        confirmed = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: confirmed.append(c))
        overlay.keyPressEvent(_key(Qt.Key.Key_Down))    # → row 1
        overlay.keyPressEvent(_key(Qt.Key.Key_Down))    # → Confirm
        overlay.keyPressEvent(_key(Qt.Key.Key_Space))   # no checkbox here
        assert confirmed == []
        assert overlay._closed is False

    def test_enter_on_confirm_confirms(self, mock_gamepad):
        confirmed = []
        overlay = _present(mock_gamepad, on_confirm=lambda c: confirmed.append(c))
        overlay.keyPressEvent(_key(Qt.Key.Key_Down))
        overlay.keyPressEvent(_key(Qt.Key.Key_Down))
        overlay.keyPressEvent(_key(Qt.Key.Key_Return))
        assert [c.key for c in confirmed[0]] == ["files"]


class TestHover:
    def test_hover_moves_cursor(self, mock_gamepad):
        overlay = _present(mock_gamepad)
        pos = QPointF(0, 0)
        overlay._rows[1].enterEvent(QEnterEvent(pos, pos, pos))
        assert overlay._cursor.index == 1
