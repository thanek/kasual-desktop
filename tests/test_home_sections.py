"""Tests for compose_home_sections — the Home Overlay sectioned model (§7.10).

Pure composition over the foreground target, brightness gating and power default;
no Qt. Labels come back localized (identity without a translator installed).
"""

from domain.menu.entry import (
    CLOSE_APP, POWER, RETURN_TO_APP, RETURN_TO_DESKTOP, TOGGLE_HUD,
)
from domain.menu.home import SectionKind, compose_home_sections
from domain.system.actions import (
    BRIGHTNESS, HIDE_DESKTOP, NETWORK, NOTIFICATIONS, RESTART, SHUTDOWN, SLEEP, VOLUME,
)
from domain.catalog.target import AppTarget, WindowTarget


class FakeHud:
    def __init__(self, available=False, enabled=True):
        self._available = available
        self._enabled = enabled

    def is_available(self):
        return self._available

    def is_enabled(self):
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False


def _desktop(brightness=True, power_default=SLEEP):
    return compose_home_sections(
        None, FakeHud(),
        brightness_controllable=brightness, power_default=power_default,
    )


def _by_kind(sections, kind):
    return next(s for s in sections.sections if s.kind == kind)


class TestDesktopContext:
    def test_sections_are_quick_then_actions(self):
        s = _desktop()
        assert [sec.kind for sec in s.sections] == [SectionKind.QUICK, SectionKind.ACTIONS]

    def test_quick_has_volume_and_brightness_when_controllable(self):
        quick = _by_kind(_desktop(brightness=True), SectionKind.QUICK)
        assert [i.action for i in quick.items] == [VOLUME, BRIGHTNESS]

    def test_quick_drops_brightness_when_not_controllable(self):
        quick = _by_kind(_desktop(brightness=False), SectionKind.QUICK)
        assert [i.action for i in quick.items] == [VOLUME]

    def test_actions_lead_with_power_then_system_grid(self):
        actions = _by_kind(_desktop(), SectionKind.ACTIONS)
        assert [i.action for i in actions.items] == [
            POWER, NETWORK, NOTIFICATIONS, HIDE_DESKTOP, RETURN_TO_DESKTOP,
        ]

    def test_return_to_home_present_so_minimized_kd_can_be_restored(self):
        # The Desktop context keeps a "Return to Home screen" card — the only way
        # back when KD is minimized (regression: it was dropped in).
        actions = _by_kind(_desktop(), SectionKind.ACTIONS)
        assert RETURN_TO_DESKTOP in [i.action for i in actions.items]

    def test_power_card_reflects_default_action(self):
        actions = _by_kind(_desktop(power_default=RESTART), SectionKind.ACTIONS)
        power = actions.items[0]
        assert power.action == POWER
        assert power.label == "Restart"            # the default's label
        assert power.icon == "fa5s.redo-alt"

    def test_power_card_default_sleep(self):
        power = _by_kind(_desktop(power_default=SLEEP), SectionKind.ACTIONS).items[0]
        assert power.label == "Sleep"

    def test_no_hud_section_on_desktop(self):
        assert all(sec.kind != SectionKind.HUD for sec in _desktop().sections)

    def test_cancel_does_not_restore(self):
        assert _desktop().cancel_restores is None


class TestAppContext:
    def _app(self, hud=None, game=False, brightness=True):
        return compose_home_sections(
            AppTarget(index=0, name="Steam"), hud or FakeHud(),
            brightness_controllable=brightness, power_default=SHUTDOWN,
            foreground_is_game=game,
        )

    def test_actions_are_app_controls(self):
        actions = _by_kind(self._app(), SectionKind.ACTIONS)
        assert [i.action for i in actions.items] == [
            RETURN_TO_APP, CLOSE_APP, RETURN_TO_DESKTOP,
        ]

    def test_labels_carry_app_name(self):
        actions = _by_kind(self._app(), SectionKind.ACTIONS)
        assert "Steam" in actions.items[0].label
        assert "Steam" in actions.items[1].label

    def test_quick_still_gated_on_brightness(self):
        quick = _by_kind(self._app(brightness=False), SectionKind.QUICK)
        assert [i.action for i in quick.items] == [VOLUME]

    def test_no_power_card_over_app(self):
        actions = _by_kind(self._app(), SectionKind.ACTIONS)
        assert all(i.action != POWER for i in actions.items)

    def test_cancel_restores_foreground(self):
        target = AppTarget(index=0, name="Steam")
        s = compose_home_sections(
            target, FakeHud(), brightness_controllable=True, power_default=SLEEP)
        assert s.cancel_restores == target

    def test_hud_section_when_game_and_available(self):
        s = self._app(hud=FakeHud(available=True), game=True)
        hud = _by_kind(s, SectionKind.HUD)
        assert [i.action for i in hud.items] == [TOGGLE_HUD]

    def test_no_hud_section_when_unavailable(self):
        s = self._app(hud=FakeHud(available=False), game=True)
        assert all(sec.kind != SectionKind.HUD for sec in s.sections)

    def test_no_hud_section_when_not_a_game(self):
        s = self._app(hud=FakeHud(available=True), game=False)
        assert all(sec.kind != SectionKind.HUD for sec in s.sections)

    def test_window_target_label_and_cancel(self):
        target = WindowTarget(window_id="w1", name="Game")
        s = compose_home_sections(
            target, FakeHud(), brightness_controllable=True, power_default=SLEEP)
        actions = _by_kind(s, SectionKind.ACTIONS)
        assert "Game" in actions.items[0].label
        assert s.cancel_restores == target
