"""Tests for HomeOverlay — the sectioned two-zone Home Overlay (§7.10).

Offscreen widget tests: drive the pad handler directly and assert zone switching,
inline slider adjustment, action dispatch, cancel, and zoned hint pushes. The
composition itself is covered by test_home_sections; here we test the widget's
navigation and side effects.
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from domain.input.vocabulary import Event
from domain.menu.entry import POWER, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.home import SectionKind
from domain.navigation import hints as nav_hints
from domain.system.actions import HIDE_DESKTOP, NETWORK, RESTART, SLEEP
from domain.system.brightness import Brightness
from domain.system.volume import Volume
from domain.catalog.target import AppTarget
from infrastructure.common.qt.overlays.home_overlay import HomeOverlay


@pytest.fixture(autouse=True)
def _dispose_overlays(qapp):
    """Delete every overlay built during the test. Each overlay is a shadowed,
    never-auto-closed top-level surface; left to pile up across the session's
    shared QApplication they eventually segfault Qt's offscreen backend. Disposing
    per test keeps the live count to one."""
    yield
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, HomeOverlay):
            widget.hide()
            widget.deleteLater()
    qapp.processEvents()


class FakeVolume:
    def __init__(self, value=50):
        self._v = Volume(value)
        self.sets = []

    def get(self):
        return self._v

    def set(self, v):
        self._v = v
        self.sets.append(v.value)


class FakeBrightness:
    def __init__(self, value=70, controllable=True):
        self._v = Brightness(value)
        self._controllable = controllable
        self.sets = []

    def get(self):
        return self._v

    def set(self, v):
        self._v = v
        self.sets.append(v.value)

    def is_controllable(self):
        return self._controllable


class FakePowerMenu:
    def __init__(self, default=SLEEP):
        self._default = default
        self.activated = 0
        self.selected = []

    def default_key(self):
        return self._default

    def activate_default(self):
        self.activated += 1

    def select(self, key):
        self.selected.append(key)


class FakeHud:
    def is_available(self): return False
    def is_enabled(self): return True
    def enable(self): ...
    def disable(self): ...


def _overlay(qapp, brightness_controllable=True):
    return HomeOverlay(
        gamepad=MagicMock(), feedback=MagicMock(),
        volume=FakeVolume(), brightness=FakeBrightness(controllable=brightness_controllable),
        power=FakePowerMenu(),
    )


def _show_desktop(overlay, on_action=None, on_cancel=None, set_hints=None,
                  desktop_minimized=False):
    overlay.show_for_context(
        foreground=None, foreground_is_game=False, hud=FakeHud(),
        on_action=on_action or (lambda i: None),
        on_cancel=on_cancel,
        set_hints=set_hints or (lambda h: None),
        desktop_minimized=desktop_minimized,
    )


def _focus_quick(o):
    """Place focus on the Quick (sliders) zone — the overlay now opens on an
    Actions card by default, so slider/cross-section tests position it first."""
    o._active = 0
    o._zones[0].index = 0
    o._render()


def _focus_actions(o, index=0):
    """Place focus on a specific card of the Actions zone (zone 1)."""
    o._active = 1
    o._zones[1].index = index
    o._render()


class TestZones:
    def test_desktop_has_quick_then_actions(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        assert [z.kind for z in o._zones] == [SectionKind.QUICK, SectionKind.ACTIONS]

    def test_quick_drops_brightness_when_not_controllable(self, qapp):
        o = _overlay(qapp, brightness_controllable=False)
        _show_desktop(o)
        assert len(o._zones[0].items) == 1   # volume only

    def test_bumpers_switch_zones(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.SECTION_NEXT)
        assert o._active == 1
        o._handle_pad(Event.SECTION_PREV)
        assert o._active == 0

    def test_bumpers_clamp_at_ends(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.SECTION_PREV)   # already first
        assert o._active == 0
        o._handle_pad(Event.SECTION_NEXT)
        o._handle_pad(Event.SECTION_NEXT)   # past last
        assert o._active == 1


class TestDefaultFocus:
    def _focused(self, o):
        zone = o._zones[o._active]
        return zone.kind, zone.items[zone.index].action

    def test_home_screen_focuses_return_to_home(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)                       # desktop visible (not minimized)
        assert self._focused(o) == (SectionKind.ACTIONS, RETURN_TO_DESKTOP)

    def test_minimized_focuses_minimize(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o, desktop_minimized=True)
        assert self._focused(o) == (SectionKind.ACTIONS, HIDE_DESKTOP)

    def test_over_app_focuses_return_to_app(self, qapp):
        o = _overlay(qapp)
        o.show_for_context(
            foreground=AppTarget(index=0, name="Steam"), foreground_is_game=False,
            hud=FakeHud(), on_action=lambda i: None, on_cancel=None,
            set_hints=lambda h: None,
        )
        assert self._focused(o) == (SectionKind.ACTIONS, RETURN_TO_APP)


class TestQuickAdjust:
    def test_right_raises_volume_live(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.RIGHT)
        assert o._volume.sets == [55]       # 50 + STEP(5)

    def test_left_lowers_volume_live(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.LEFT)
        assert o._volume.sets == [45]

    def test_down_moves_to_brightness_then_adjusts_it(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.DOWN)           # quick index 0 → 1 (brightness)
        o._handle_pad(Event.RIGHT)
        assert o._brightness.sets == [80]   # 70 + STEP(10)
        assert o._volume.sets == []         # volume untouched


class TestCrossSectionNav:
    def test_down_from_last_slider_enters_actions(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)                    # quick = [volume, brightness]
        _focus_quick(o)
        o._handle_pad(Event.DOWN)           # volume → brightness (last quick item)
        o._handle_pad(Event.DOWN)           # spills into the Actions section
        assert o._active == 1
        assert o._zones[1].index == 0       # lands on the first card (power)

    def test_up_from_actions_top_row_enters_quick(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_actions(o, 0)                # Actions top row
        o._handle_pad(Event.UP)             # top row spills back into Quick
        assert o._active == 0
        assert o._zones[0].index == 1       # lands on the last slider (brightness)

    def test_up_from_first_slider_clamps(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_quick(o)
        o._handle_pad(Event.UP)             # nothing above the first section
        assert o._active == 0
        assert o._zones[0].index == 0

    def test_down_reaches_second_actions_row(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)                    # Actions: power(0) network(1) notif(2) / minimize(3) home(4)
        _focus_actions(o, 0)
        o._handle_pad(Event.DOWN)           # power → minimize (row 2)
        assert o._zones[1].index == 3
        o._handle_pad(Event.RIGHT)          # minimize → return-home
        assert o._zones[1].index == 4

    def test_down_from_partial_row_gap_snaps_to_last(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_actions(o, 0)
        o._handle_pad(Event.RIGHT)          # power → network
        o._handle_pad(Event.RIGHT)          # network → notifications (col 2, nothing below)
        o._handle_pad(Event.DOWN)           # snaps to the last card of the partial row
        assert o._zones[1].index == 4       # return-home, not a dead end


class TestActions:
    def test_select_network_dispatches_and_closes(self, qapp):
        dispatched = []
        o = _overlay(qapp)
        _show_desktop(o, on_action=lambda i: dispatched.append(i))
        _focus_actions(o, 0)
        o._handle_pad(Event.RIGHT)          # power(0) → network(1)
        o._handle_pad(Event.SELECT)
        assert [i.action for i in dispatched] == [NETWORK]
        assert o.is_showing() is False

    def test_power_card_runs_default_not_dispatch(self, qapp):
        dispatched = []
        o = _overlay(qapp)
        _show_desktop(o, on_action=lambda i: dispatched.append(i))
        _focus_actions(o, 0)                # focus power card (index 0)
        o._handle_pad(Event.SELECT)
        assert o._power.activated == 1
        assert dispatched == []             # POWER is handled internally
        assert o.is_showing() is False

    def test_grid_navigation_clamps(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        _focus_actions(o, 0)
        zone = o._zones[1]
        o._handle_pad(Event.LEFT)           # already col 0 → stays
        assert zone.index == 0
        o._handle_pad(Event.DOWN)           # row 0 → row 1 (index 0 → 3)
        assert zone.index == 3


class TestVolumeTriggers:
    def test_triggers_adjust_volume_from_any_zone(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)                    # opens on the Actions grid, not a slider
        o._handle_pad(Event.VOLUME_UP)
        assert o._volume.sets == [55]       # still adjusts, regardless of focus
        o._handle_pad(Event.VOLUME_DOWN)
        assert o._volume.sets == [55, 50]

    def test_trigger_reflects_in_quick_slider_state(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        o._handle_pad(Event.VOLUME_UP)
        # The Quick slider's cached value tracks the trigger, so returning to it
        # and nudging continues from the new value (no drift).
        assert o._volume_state()["value"].value == 55


class TestPowerDropdown:
    def _focus_power(self, o):
        _focus_actions(o, 0)                # Actions zone, power card at index 0

    def test_y_opens_dropdown_at_current_default(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        self._focus_power(o)
        o._handle_pad(Event.ACTIONS)
        assert o._dropdown is not None
        assert o._dropdown["index"] == 0    # default is SLEEP, first in the list

    def test_y_on_non_power_card_does_nothing(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        self._focus_power(o)
        o._handle_pad(Event.RIGHT)          # power(0) → network(1)
        o._handle_pad(Event.ACTIONS)
        assert o._dropdown is None

    def test_pick_runs_select_and_closes_overlay(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        self._focus_power(o)
        o._handle_pad(Event.ACTIONS)
        o._handle_pad(Event.DOWN)           # SLEEP → RESTART
        o._handle_pad(Event.SELECT)
        assert o._power.selected == [RESTART]
        assert o._dropdown is None
        assert o.is_showing() is False

    def test_b_closes_dropdown_not_overlay(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        self._focus_power(o)
        o._handle_pad(Event.ACTIONS)
        o._handle_pad(Event.CANCEL)
        assert o._dropdown is None
        assert o.is_showing() is True       # back to the Actions grid, still open

    def test_triggers_work_while_dropdown_open(self, qapp):
        o = _overlay(qapp)
        _show_desktop(o)
        self._focus_power(o)
        o._handle_pad(Event.ACTIONS)
        o._handle_pad(Event.VOLUME_UP)
        assert o._volume.sets == [55]
        assert o._dropdown is not None      # volume nudge doesn't dismiss it


class TestCancelAndHints:
    def test_cancel_invokes_on_cancel_and_closes(self, qapp):
        cancelled = []
        o = _overlay(qapp)
        _show_desktop(o, on_cancel=lambda: cancelled.append(1))
        o._handle_pad(Event.CANCEL)
        assert cancelled == [1]
        assert o.is_showing() is False

    def test_hints_follow_active_zone(self, qapp):
        pushed = []
        o = _overlay(qapp)
        _show_desktop(o, set_hints=lambda h: pushed.append(h))
        assert pushed[-1] is nav_hints.OVERLAY_ACTIONS   # opens on an Actions card
        o._handle_pad(Event.SECTION_PREV)
        assert pushed[-1] is nav_hints.OVERLAY_QUICK


class TestAppContext:
    def test_app_actions_dispatch(self, qapp):
        dispatched = []
        o = _overlay(qapp)
        o.show_for_context(
            foreground=AppTarget(index=0, name="Steam"), foreground_is_game=False,
            hud=FakeHud(), on_action=lambda i: dispatched.append(i),
            on_cancel=None, set_hints=lambda h: None,
        )
        # Actions zone is second; quick (volume+brightness) first.
        assert [z.kind for z in o._zones] == [SectionKind.QUICK, SectionKind.ACTIONS]
        # Opens already focused on "Return to {app}", so A dispatches it straight away.
        o._handle_pad(Event.SELECT)
        assert [i.action for i in dispatched] == [RETURN_TO_APP]
