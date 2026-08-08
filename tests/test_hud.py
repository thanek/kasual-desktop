"""Tests for the HUD toggle's rough logic — hud_menu_item / toggle_hud.

Pure decisions over a HudControl stub, the foreground-is-game flag and the pid the
game renders through; no filesystem, no Qt. Labels come back localized; with no translator installed
`support.i18n` is the identity, so they equal the source strings.
"""

from domain.catalog.app import App
from domain.menu.entry import TOGGLE_HUD
from domain.system.hud import hud_launch_env, hud_menu_item, toggle_hud


ARMED_PID   = 1234   # the FakeHud is loaded into this one
UNARMED_PID = 999


class FakeHud:
    def __init__(self, available=True, enabled=True, env=None,
                 attached_pids=(ARMED_PID,)):
        self._available = available
        self.enabled = enabled
        self._env = env if env is not None else {"MANGOHUD": "1"}
        self._attached_pids = attached_pids

    def is_available(self): return self._available
    def is_enabled(self): return self.enabled
    def enable(self): self.enabled = True
    def disable(self): self.enabled = False
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

    def test_disable_label_while_on(self):
        item = _item(FakeHud(available=True, enabled=True))
        assert item.action == TOGGLE_HUD
        assert item.label == "Disable HUD"

    def test_enable_label_while_off(self):
        item = _item(FakeHud(available=True, enabled=False))
        assert item.action == TOGGLE_HUD
        assert item.label == "Enable HUD"


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
        assert hud_launch_env(FakeHud(enabled=False), self._app(("Game",))) == {"MANGOHUD": "1"}


class TestToggle:
    def test_on_turns_off(self):
        hud = FakeHud(enabled=True)
        toggle_hud(hud)
        assert hud.enabled is False

    def test_off_turns_on(self):
        hud = FakeHud(enabled=False)
        toggle_hud(hud)
        assert hud.enabled is True
