"""Tests for HomeSurface — the persistent collapse/expand Home-view surface (§8 / Faza 5).

Offscreen widget tests: drive expand/collapse and the embedded content's pad
handler, asserting the morph state, the gamepad handler push/pop, the hint
begin/end bracketing, and that activating an item dispatches and collapses. The
sectioned content's own navigation is covered by test_home_overlay (same widget).
"""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from domain.catalog.target import AppTarget
from domain.input.vocabulary import Event
from domain.menu.entry import POWER, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.system.actions import NETWORK
from domain.system.brightness import Brightness
from domain.system.volume import Volume
from infrastructure.common.qt.desktop.home_surface import HomeSurface


@pytest.fixture(autouse=True)
def _dispose(qapp):
    yield
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, HomeSurface):
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

    def get(self):
        return self._v

    def set(self, v):
        self._v = v

    def is_controllable(self):
        return self._controllable


class FakePowerMenu:
    def __init__(self):
        self.activated = 0

    def default_key(self):
        from domain.system.actions import SLEEP
        return SLEEP

    def activate_default(self):
        self.activated += 1

    def select(self, key):
        ...


class Spy:
    """Records calls so the test can assert the dispatch/hint bracketing."""

    def __init__(self):
        self.actions = []
        self.hints = []          # True begin, False end
        self.pushed_hints = []
        self.header_activations = []
        self.power_choosers = 0

    def on_action(self, item):
        self.actions.append(item.action)

    def on_header_activate(self, action):
        self.header_activations.append(action)

    def on_power_chooser(self):
        self.power_choosers += 1

    def begin_hints(self):
        self.hints.append(True)

    def set_hints(self, hints):
        self.pushed_hints.append(hints)

    def end_hints(self):
        self.hints.append(False)


def _surface(qapp, gamepad=None, spy=None):
    from infrastructure.common.qt.overlays.home_header import HomeHeader
    from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH
    spy = spy or Spy()
    header = HomeHeader(spy.on_header_activate, CARD_WIDTH)
    surface = HomeSurface(
        gamepad or MagicMock(), MagicMock(),
        FakeVolume(), FakeBrightness(), FakePowerMenu(), header,
        on_action=spy.on_action,
        on_power_chooser=spy.on_power_chooser,
        begin_hints=spy.begin_hints,
        set_hints=spy.set_hints,
        end_hints=spy.end_hints,
    )
    return surface, spy


class TestMorphState:
    def test_starts_collapsed(self, qapp):
        surface, _ = _surface(qapp)
        assert surface.is_expanded() is False

    def test_expand_then_collapse(self, qapp):
        surface, _ = _surface(qapp)
        surface.expand()
        assert surface.is_expanded() is True
        surface.collapse()
        assert surface.is_expanded() is False

    def test_expand_is_idempotent(self, qapp):
        gp = MagicMock()
        surface, _ = _surface(qapp, gamepad=gp)
        surface.expand()
        surface.expand()
        assert gp.push_handler.call_count == 1   # second expand is a no-op


class TestPadAndHints:
    def test_expand_pushes_handler_and_begins_hints(self, qapp):
        gp = MagicMock()
        surface, spy = _surface(qapp, gamepad=gp)
        surface.expand()
        gp.push_handler.assert_called_once()
        assert spy.hints[0] is True

    def test_collapse_pops_handler_and_ends_hints(self, qapp):
        gp = MagicMock()
        surface, spy = _surface(qapp, gamepad=gp)
        surface.expand()
        surface.collapse()
        gp.pop_handler.assert_called_once()
        assert spy.hints[-1] is False

    def test_collapse_pops_the_same_handler_it_pushed(self, qapp):
        # The focus stack removes by equality (list.remove), and bound methods are
        # equal by (func, instance) — so the popped handler must compare equal to
        # the pushed one, even though each attribute access yields a fresh object.
        gp = MagicMock()
        surface, _ = _surface(qapp, gamepad=gp)
        surface.expand()
        surface.collapse()
        assert (gp.push_handler.call_args.args[0]
                == gp.pop_handler.call_args.args[0])


class TestDispatch:
    def test_select_default_dispatches_return_home_and_collapses(self, qapp):
        # Context 1 opens focused on "Return to Home screen"; A dispatches it.
        surface, spy = _surface(qapp)
        surface.expand()
        surface._content.handle_pad(Event.SELECT)
        assert spy.actions == [RETURN_TO_DESKTOP]
        assert surface.is_expanded() is False

    def test_select_network_in_header_dispatches_and_collapses(self, qapp):
        # Network lives on the header (zone 0) when a header is present, not in the
        # Actions grid; selecting it there dispatches and collapses.
        surface, spy = _surface(qapp)
        surface.expand()
        content = surface._content
        zi, ci = next((zi, ci)
                      for zi, z in enumerate(content._zones)
                      for ci, it in enumerate(z.items) if it.action == NETWORK)
        content._active, content._zones[zi].index = zi, ci
        content.handle_pad(Event.SELECT)
        assert spy.actions == [NETWORK]
        assert surface.is_expanded() is False

    def test_network_not_duplicated_in_actions_grid(self, qapp):
        surface, _ = _surface(qapp)
        surface.expand()
        from domain.menu.home import SectionKind
        actions = next(z for z in surface._content._zones
                       if z.kind == SectionKind.ACTIONS)
        assert all(it.action != NETWORK for it in actions.items)

    def test_up_from_actions_reaches_header(self, qapp):
        # "Up" from the menu's top section must flow into the header (zone 0).
        surface, spy = _surface(qapp)
        surface.expand()
        content = surface._content
        from domain.menu.home import SectionKind
        # Walk up until we land on the header zone (header ← quick ← actions).
        for _ in range(5):
            if content._zones[content._active].kind == SectionKind.HEADER:
                break
            content.handle_pad(Event.UP)
        assert content._zones[content._active].kind == SectionKind.HEADER
        # The header navigates left/right, so its hint set advertises that (not the
        # up/down of the Actions list).
        from domain.navigation import hints as nav_hints
        assert spy.pushed_hints[-1] is nav_hints.OVERLAY_HEADER

    def test_actions_zone_uses_list_hints(self, qapp):
        # The Actions section is a vertical list: its hints navigate up/down only.
        surface, spy = _surface(qapp)
        surface.expand()
        from domain.menu.home import SectionKind
        from domain.navigation import hints as nav_hints
        assert surface._content._zones[surface._content._active].kind == SectionKind.ACTIONS
        assert spy.pushed_hints[-1] is nav_hints.OVERLAY_ACTIONS

    def _focus_header_power(self, content):
        zi, ci = next((zi, ci)
                      for zi, z in enumerate(content._zones)
                      for ci, it in enumerate(z.items) if it.action == POWER)
        content._active, content._zones[zi].index = zi, ci

    def test_power_in_header_A_runs_default_and_collapses(self, qapp):
        # A on the header's Power runs the current default action and collapses the
        # menu — it does not open the chooser (§8; Y opens the chooser).
        surface, spy = _surface(qapp)
        surface.expand()
        content = surface._content
        self._focus_header_power(content)
        content.handle_pad(Event.SELECT)
        assert content._power.activated == 1
        assert spy.power_choosers == 0
        assert spy.actions == []
        assert surface.is_expanded() is False

    def test_power_in_header_X_opens_chooser_and_keeps_menu(self, qapp):
        # X on the header's Power (the tile-popover button) opens the chooser
        # without running an action or collapsing the menu (it floats over it).
        surface, spy = _surface(qapp)
        surface.expand()
        content = surface._content
        self._focus_header_power(content)
        content.handle_pad(Event.CLOSE)
        assert spy.power_choosers == 1
        assert content._power.activated == 0
        assert spy.actions == []
        assert surface.is_expanded() is True       # menu stays open behind chooser

    def test_power_not_in_actions_grid(self, qapp):
        surface, _ = _surface(qapp)
        surface.expand()
        from domain.menu.home import SectionKind
        actions = next(z for z in surface._content._zones
                       if z.kind == SectionKind.ACTIONS)
        assert all(it.action != POWER for it in actions.items)

    def test_b_collapses_without_dispatch(self, qapp):
        surface, spy = _surface(qapp)
        surface.expand()
        surface._content.handle_pad(Event.CANCEL)
        assert spy.actions == []
        assert surface.is_expanded() is False


class TestHeaderAsTopBar:
    """The header doubles as the FocusNavigator's top bar in the collapsed Home
    view: "up" from the tiles enters it, A opens Network / Notifications."""

    def _nav_with_header(self):
        from infrastructure.common.qt.overlays.home_header import HomeHeader
        from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH
        from domain.navigation.focus_navigator import FocusNavigator
        activated = []
        header = HomeHeader(activated.append, CARD_WIDTH)
        tilebar = MagicMock()
        tilebar.move.return_value = True
        tilebar.current_is_add.return_value = False
        nav = FocusNavigator(tilebar, header, on_tile_menu=MagicMock(),
                             feedback=MagicMock(), gamepad=MagicMock())
        return nav, header, activated

    def test_up_from_tiles_enters_header(self, qapp):
        nav, *_ = self._nav_with_header()
        assert nav.in_tiles is True
        nav.handle_pad(Event.UP)
        assert nav.in_tiles is False

    def test_select_in_header_opens_network(self, qapp):
        nav, _header, activated = self._nav_with_header()
        nav.handle_pad(Event.UP)         # into the header (index 0 = Network)
        nav.handle_pad(Event.SELECT)
        assert activated == ["network"]

    def test_right_then_select_opens_notifications(self, qapp):
        nav, _header, activated = self._nav_with_header()
        nav.handle_pad(Event.UP)
        nav.handle_pad(Event.RIGHT)      # Network → Notifications
        nav.handle_pad(Event.SELECT)
        assert activated == ["notifications"]

    def test_power_is_rightmost_and_triggers_power(self, qapp):
        nav, _header, activated = self._nav_with_header()
        nav.handle_pad(Event.UP)
        nav.handle_pad(Event.RIGHT)      # Network → Notifications
        nav.handle_pad(Event.RIGHT)      # Notifications → Power (far right)
        nav.handle_pad(Event.SELECT)
        assert activated == [POWER]

    def test_set_power_icon_changes_glyph(self, qapp):
        from infrastructure.common.qt.overlays.home_header import HomeHeader
        from infrastructure.common.qt.overlays.home_menu_content import CARD_WIDTH
        header = HomeHeader(lambda a: None, CARD_WIDTH)
        before = header.power_button().icon().cacheKey()
        header.set_power_icon("fa5s.moon")
        assert header.power_button().icon().cacheKey() != before


class TestOnDemand:
    """Contexts 2/3: the controller drives the surface as a SectionedHomeOverlay —
    mapped expanded on show_for_context, unmapped on hide_overlay."""

    def _show_over_app(self, surface, on_action=None, on_cancel=None):
        surface.show_for_context(
            foreground=AppTarget(index=0, name="Steam"), foreground_is_game=False,
            hud=FakeHud(),
            on_action=on_action or (lambda i: None),
            on_cancel=on_cancel,
            set_hints=lambda h: None,
        )

    def test_show_for_context_marks_showing(self, qapp):
        surface, _ = _surface(qapp)
        self._show_over_app(surface)
        assert surface.is_showing() is True
        assert surface.isVisible() is True

    def test_hide_overlay_hides_and_emits_closed(self, qapp):
        surface, _ = _surface(qapp)
        closed = []
        surface.on_closed(lambda: closed.append(1))
        self._show_over_app(surface)
        surface.hide_overlay()
        assert surface.is_showing() is False
        assert closed == [1]

    def test_app_action_dispatches_and_hides(self, qapp):
        surface, _ = _surface(qapp)
        dispatched = []
        self._show_over_app(surface, on_action=dispatched.append)
        # Opens pre-focused on "Return to {app}"; A dispatches it and hides.
        surface._content.handle_pad(Event.SELECT)
        assert [i.action for i in dispatched] == [RETURN_TO_APP]
        assert surface.is_showing() is False

    def test_dispose_is_noop(self, qapp):
        surface, _ = _surface(qapp)
        surface.dispose()        # persistent surface — must not raise or delete
        self._show_over_app(surface)
        assert surface.is_showing() is True

    def test_return_to_desktop_tears_down_the_on_demand_overlay(self, qapp):
        # The reported bug: picking "Return to Home screen" over an app must close
        # the on-demand overlay, not leave its (stale) app-context menu mapped.
        surface, _ = _surface(qapp)
        dispatched = []
        self._show_over_app(surface, on_action=dispatched.append)
        # Focus the "Return to Home screen" card and activate it.
        content = surface._content
        zi, ci = next((zi, ci)
                      for zi, z in enumerate(content._zones)
                      for ci, it in enumerate(z.items)
                      if it.action == RETURN_TO_DESKTOP)
        content._active, content._zones[zi].index = zi, ci
        content.handle_pad(Event.SELECT)
        assert [i.action for i in dispatched] == [RETURN_TO_DESKTOP]
        assert surface.is_showing() is False        # overlay torn down, not left up
        assert surface._panel.maximumHeight() == 0  # collapsed, not the expanded menu

    def test_dismiss_closes_the_live_mode_regardless_of_wiring(self, qapp):
        # request_hide is wired to dismiss() in both contexts; it must close the
        # mode that is actually open. On-demand → hidden.
        surface, _ = _surface(qapp)
        self._show_over_app(surface)
        surface.dismiss()
        assert surface.is_showing() is False
        # Context 1 morph → collapsed.
        surface.expand()
        surface.dismiss()
        assert surface.is_expanded() is False

    def test_collapse_immediately_reclaims_a_stale_on_demand_overlay(self, qapp):
        # The Desktop's visibility sync calls this to reclaim an on-demand overlay
        # left mapped when the Desktop comes forward (belt-and-suspenders for the
        # bug above).
        gp = MagicMock()
        surface, _ = _surface(qapp, gamepad=gp)
        self._show_over_app(surface)
        surface.collapse_immediately()
        assert surface.is_showing() is False
        assert surface._panel.maximumHeight() == 0
        gp.pop_handler.assert_called_once()


class FakeHud:
    def is_available(self): return False
    def is_enabled(self): return True
    def enable(self): ...
    def disable(self): ...


class TestStatusHeader:
    def test_network_and_badge_setters_do_not_crash(self, qapp):
        surface, _ = _surface(qapp)
        surface.set_network_icon("fa5s.wifi")
        surface.set_notification_badge(3)
        surface.set_notification_badge(0)

    def test_collapse_immediately_from_expanded_resets(self, qapp):
        gp = MagicMock()
        surface, _ = _surface(qapp, gamepad=gp)
        surface.expand()
        surface.collapse_immediately()
        assert surface.is_expanded() is False
        gp.pop_handler.assert_called_once()
