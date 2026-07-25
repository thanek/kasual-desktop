"""The X11 side of the COSMIC adapter: which window a toplevel is, and who gets
asked to go fullscreen. The X server is stubbed at the snapshot/request seam."""

from unittest.mock import patch

from infrastructure.cosmic.wm.fullscreen import ForegroundFullscreen
from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.cosmic.wm.xwayland import (
    X11Window, _fills_an_output, _is_resizable, match,
)

GAME = "steam_app_620"


def _toplevel(app_id=GAME, title="The Witcher", identifier="id", **state):
    state.setdefault("activated", True)
    return Toplevel(identifier=identifier, title=title, app_id=app_id, **state)


def _x11(app_id=GAME, title="The Witcher", pid=500, window_id=7, **kwargs):
    return X11Window(classes=(app_id, app_id), title=title, pid=pid,
                     window_id=window_id, **kwargs)


class TestMatch:
    def test_matches_on_window_class(self):
        assert match([_x11()], _toplevel()).pid == 500

    def test_title_separates_two_instances_of_one_app(self):
        windows = [_x11("term", "left", pid=1), _x11("term", "right", pid=2)]
        assert match(windows, _toplevel("term", title="right")).pid == 2

    def test_ambiguous_without_a_title_match(self):
        windows = [_x11("term", "left", pid=1), _x11("term", "right", pid=2)]
        assert match(windows, _toplevel("term", title="other")) is None

    def test_unknown_class_finds_nothing(self):
        assert match([_x11("term", "left")], _toplevel("firefox")) is None


class TestFillsAnOutput:
    def test_a_window_the_size_of_a_monitor_fills_it(self):
        assert _fills_an_output(_Geometry(2560, 1440), [(2560, 1440)]) is True

    def test_a_maximized_window_stops_at_the_work_area(self):
        assert _fills_an_output(_Geometry(2560, 1392), [(2560, 1440)]) is False

    def test_the_second_monitor_counts_too(self):
        assert _fills_an_output(_Geometry(1920, 1080),
                                [(2560, 1440), (1920, 1080)]) is True


class TestIsResizable:
    def test_a_window_that_pins_its_size_is_not(self):
        assert _is_resizable(_Hints(812, 416, 812, 416)) is False

    def test_a_window_free_to_grow_is(self):
        assert _is_resizable(_Hints(0, 0, 0, 0)) is True

    def test_a_minimum_alone_does_not_pin_it(self):
        assert _is_resizable(_Hints(640, 480, 0, 0)) is True

    def test_no_hints_at_all_leaves_it_free(self):
        assert _is_resizable(None) is True


class _Geometry:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class _Hints:
    def __init__(self, min_width, min_height, max_width, max_height):
        self.min_width = min_width
        self.min_height = min_height
        self.max_width = max_width
        self.max_height = max_height


class FakeXWayland:
    def __init__(self, focused=None):
        self.focused = focused
        self.asked: list[int] = []

    def focused_window(self, windows):
        return next((w for w in windows if w.window_id == self.focused), None)

    def ask_fullscreen(self, window):
        self.asked.append(window.window_id)


class TestForegroundFullscreen:
    """`at` is when a refresh happens; a window is asked for only once it has
    settled, so an ask takes two refreshes."""

    def _fullscreen(self, focused=7):
        xwayland = FakeXWayland(focused)
        fullscreen = ForegroundFullscreen(xwayland)
        fullscreen.screen_given_to_app()
        return xwayland, fullscreen

    @staticmethod
    def _refresh(fullscreen, toplevels, x11, at):
        with patch("infrastructure.cosmic.wm.fullscreen.time.monotonic",
                   return_value=at):
            fullscreen.apply(toplevels, x11)

    def _asked_for(self, toplevels, x11, focused=7):
        xwayland, fullscreen = self._fullscreen(focused)
        self._refresh(fullscreen, toplevels, x11, at=0.0)
        self._refresh(fullscreen, toplevels, x11, at=5.0)
        return xwayland.asked

    def test_the_app_in_front_is_given_the_screen(self):
        assert self._asked_for([_toplevel()], [_x11()]) == [7]

    def test_nothing_is_asked_for_while_kasual_holds_the_screen(self):
        xwayland = FakeXWayland(7)
        fullscreen = ForegroundFullscreen(xwayland)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=0.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=5.0)
        assert xwayland.asked == []

    def test_a_window_that_has_only_just_mapped_is_left_to_settle(self):
        xwayland, fullscreen = self._fullscreen()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=0.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=1.0)
        assert xwayland.asked == []

    def test_an_ask_nobody_heard_is_repeated(self):
        xwayland, fullscreen = self._fullscreen()
        for at in (0.0, 5.0, 11.0, 17.0):
            self._refresh(fullscreen, [_toplevel()], [_x11()], at=at)
        assert xwayland.asked == [7, 7, 7]

    def test_asks_do_not_pile_up_between_refreshes(self):
        xwayland, fullscreen = self._fullscreen()
        for at in (0.0, 5.0, 6.0, 7.0, 8.0):
            self._refresh(fullscreen, [_toplevel()], [_x11()], at=at)
        assert xwayland.asked == [7]

    def test_a_compositor_that_means_no_is_not_fought_forever(self):
        xwayland, fullscreen = self._fullscreen()
        for at in range(0, 200, 6):
            self._refresh(fullscreen, [_toplevel()], [_x11()], at=float(at))
        assert len(xwayland.asked) == 5

    def test_the_screen_taken_back_stops_the_asking(self):
        xwayland, fullscreen = self._fullscreen()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=0.0)
        fullscreen.screen_taken_back()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=5.0)
        assert xwayland.asked == []

    def test_coming_back_to_the_app_asks_again(self):
        xwayland, fullscreen = self._fullscreen()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=0.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=5.0)
        fullscreen.screen_taken_back()
        fullscreen.screen_given_to_app()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=20.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=25.0)
        assert xwayland.asked == [7, 7]

    def test_a_window_already_fullscreen_is_left_alone(self):
        assert self._asked_for([_toplevel(fullscreen=True)],
                               [_x11(fullscreen=True)]) == []

    def test_a_minimized_toplevel_is_left_where_it_is(self):
        assert self._asked_for([_toplevel(minimized=True)], [_x11()]) == []

    def test_a_toplevel_cosmic_does_not_call_activated_is_left_alone(self):
        assert self._asked_for([_toplevel(activated=False)], [_x11()]) == []

    def test_the_focus_left_behind_by_a_wayland_app_is_left_alone(self):
        assert self._asked_for([_toplevel("com.system76.CosmicTerm")], [_x11()]) == []

    def test_an_unfocused_window_of_the_app_is_left_alone(self):
        assert self._asked_for([_toplevel()], [_x11(window_id=8)], focused=7) == []

    def test_a_splash_that_pins_its_size_is_left_alone(self):
        assert self._asked_for([_toplevel()], [_x11(resizable=False)]) == []

    def test_a_splash_is_asked_for_once_it_fills_the_screen_anyway(self):
        assert self._asked_for(
            [_toplevel()], [_x11(resizable=False, covers_screen=True)]) == [7]

    def test_a_dialog_is_not_a_fullscreen_candidate(self):
        assert self._asked_for([_toplevel()], [_x11(ordinary=False)]) == []

    def test_a_wayland_only_app_has_nothing_to_ask_through(self):
        assert self._asked_for([_toplevel()], []) == []

    def test_a_window_that_came_and_went_is_not_remembered(self):
        xwayland, fullscreen = self._fullscreen()
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=0.0)
        self._refresh(fullscreen, [], [], at=5.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=10.0)
        self._refresh(fullscreen, [_toplevel()], [_x11()], at=13.0)
        assert xwayland.asked == [7]
