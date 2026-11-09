"""Tests for the HUD slider's logic — HudLevel, hud_menu_item, hud_launch_env.

Pure decisions over a HudControl stub, the foreground-is-game flag and the pid the
game renders through; no filesystem, no Qt. Labels come back localized; with no translator installed
`support.i18n` is the identity, so they equal the source strings.
"""

from domain.catalog.app import App
from domain.menu.entry import HUD_LEVEL
from domain.system.hud import HUD_OFF, HudLevel, hud_launch_env, hud_menu_item


ARMED_PID   = 1234   # the FakeHud is loaded into this one
UNARMED_PID = 999


class FakeHud:
    def __init__(self, available=True, level=2, env=None,
                 attached_pids=(ARMED_PID,)):
        self._available = available
        self.current = HudLevel(level, 4)
        self._env = env if env is not None else {"MANGOHUD": "1"}
        self._attached_pids = attached_pids

    def is_available(self): return self._available
    def level(self): return self.current
    def set_level(self, level): self.current = level
    def launch_env(self): return self._env
    def is_attached(self, pid): return pid in self._attached_pids


def _item(hud, *, game=True, pid=ARMED_PID):
    return hud_menu_item(hud, game, pid)


class TestMenuItem:
    def test_none_when_unavailable(self):
        assert _item(FakeHud(available=False)) is None

    def test_none_when_not_a_game(self):
        assert _item(FakeHud(available=True), game=False) is None

    def test_offered_for_game(self):
        assert _item(FakeHud(available=True)) is not None

    def test_none_when_the_game_does_not_carry_the_hud(self):
        """The toggle would flip a state nothing on screen reads."""
        assert _item(FakeHud(available=True), pid=UNARMED_PID) is None

    def test_none_without_a_process_to_ask(self):
        assert _item(FakeHud(available=True), pid=None) is None

    def test_the_slider_names_the_overlay_whatever_its_level(self):
        for level in (HUD_OFF, 3):
            item = _item(FakeHud(level=level))
            assert item.action == HUD_LEVEL
            assert item.label == "Performance overlay"


class TestLaunchEnv:
    def _app(self, categories=()):
        return App(name="App", command="prog", categories=categories)

    def test_game_gets_the_huds_environment(self):
        assert hud_launch_env(FakeHud(), self._app(("Game",))) == {"MANGOHUD": "1"}

    def test_nothing_for_a_non_game(self):
        assert hud_launch_env(FakeHud(), self._app(("Utility",))) == {}

    def test_nothing_when_the_hud_is_unconfigured(self):
        assert hud_launch_env(FakeHud(available=False), self._app(("Game",))) == {}

    def test_off_state_still_arms_the_game(self):
        """The layer must load even while hidden, or re-enabling would need a restart."""
        assert hud_launch_env(FakeHud(level=HUD_OFF), self._app(("Game",))) == {"MANGOHUD": "1"}


class TestHudLevel:
    def test_clamps_into_range(self):
        assert HudLevel(9, 4).value == 4
        assert HudLevel(-1, 4).value == HUD_OFF

    def test_steps_stop_at_the_ends(self):
        assert HudLevel(4, 4).adjusted(+1).value == 4
        assert HudLevel(HUD_OFF, 4).adjusted(-1).value == HUD_OFF

    def test_steps_one_level_at_a_time(self):
        assert HudLevel(2, 4).adjusted(+1) == HudLevel(3, 4)

    def test_off_reads_as_off(self):
        assert HudLevel(HUD_OFF, 4).is_off
        assert HudLevel(HUD_OFF, 4).label == "Off"

    def test_detail_level_reads_as_its_number(self):
        assert HudLevel(3, 4).label == "3"
