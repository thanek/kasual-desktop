"""Domain coverage for the UX input foundation.

Pure domain — no Qt, no device backend. Verifies the new abstract events exist
with stable string values (they flow through the StrEnum/pyqtSignal transport as
plain strings) and that the Home Overlay's zoned hint bars (§7.10) are wired with
the bumper/trigger glyphs the widget will render.
"""

from domain.input.vocabulary import Event
from domain.navigation import hints
from domain.navigation.hints import Button, ButtonHint, Direction


# ── Vocabulary ──────────────────────────────────────────────────────────────

class TestNewEvents:
    def test_values_are_stable_strings(self):
        # The transport compares these against bare literals during migration, so
        # the string values are part of the contract.
        assert Event.SECTION_PREV == "section_prev"
        assert Event.SECTION_NEXT == "section_next"
        assert Event.VOLUME_DOWN  == "volume_down"
        assert Event.VOLUME_UP    == "volume_up"
        assert Event.ACTIONS      == "actions"


# ── Hint glyphs ──────────────────────────────────────────────────────────────

class TestButtons:
    def test_bumper_and_trigger_glyphs_exist(self):
        assert {Button.LB, Button.RB, Button.LT, Button.RT} <= set(Button)


# ── Zoned Home Overlay hint bars ─────────────────────────────────────────────

def _buttons(hints_set, attr):
    return [h.button for h in getattr(hints_set, attr)]


def _directions(hints_set, attr):
    return list(getattr(hints_set, attr))


class TestOverlayQuickHints:
    def test_bumpers_switch_sections(self):
        assert _buttons(hints.OVERLAY_QUICK, "bumpers") == [Button.LB, Button.RB]

    def test_triggers_are_volume(self):
        assert _buttons(hints.OVERLAY_QUICK, "triggers") == [Button.LT, Button.RT]

    def test_two_clusters_read_axes_apart(self):
        # ↕ moves between sliders/sections ("Navigate"); ◄► commits live ("Adjust").
        assert hints.OVERLAY_QUICK.nav_label == "Navigate"
        assert hints.OVERLAY_QUICK.adjust_label == "Adjust"
        assert _directions(hints.OVERLAY_QUICK, "directions") == [Direction.UP, Direction.DOWN]
        assert _directions(hints.OVERLAY_QUICK, "adjust") == [Direction.LEFT, Direction.RIGHT]

    def test_no_select_action(self):
        # Quick adjust has no A — there is nothing to confirm, only B to leave.
        assert _buttons(hints.OVERLAY_QUICK, "actions") == [Button.B]


class TestOverlayActionsHints:
    def test_bumpers_switch_sections(self):
        assert _buttons(hints.OVERLAY_ACTIONS, "bumpers") == [Button.LB, Button.RB]

    def test_y_expands_dropdown(self):
        # Y (ACTIONS) expands the Power split-button.
        assert Button.Y in _buttons(hints.OVERLAY_ACTIONS, "actions")

    def test_grid_has_select_and_back(self):
        actions = _buttons(hints.OVERLAY_ACTIONS, "actions")
        assert Button.A in actions and Button.B in actions


class TestClassicHintsUnchanged:
    def test_tiles_have_no_bumpers(self):
        # The bumper/trigger fields default empty on the Surface screens.
        assert hints.TILES.bumpers == ()
        assert hints.TILES.triggers == ()
