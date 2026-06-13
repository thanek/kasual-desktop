"""Tests for the Application controller — wiring over domain ports only.

The controller is pure wiring (no Qt): it subscribes to the gamepad through the
`GamepadSignals` port, creates overlays through the `OverlayFactory` port, and
routes activated menu items. Here we drive it entirely over fakes.
"""

from application import Application
from domain.shared.event_emitter import EventEmitter
from domain.input.gamepad_events import (
    BtnModePressed, GamepadConnected, GamepadDisconnected,
)
from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.item import MenuItem
from domain.system.actions import ActionDeps, VOLUME
from domain.catalog.app import App


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeGamepad:
    """GamepadSignals port over real EventEmitters, with fire helpers."""

    def __init__(self):
        self._btn_mode = EventEmitter[BtnModePressed]()
        self._connected = EventEmitter[GamepadConnected]()
        self._disconnected = EventEmitter[GamepadDisconnected]()

    def on_btn_mode(self, handler):
        return self._btn_mode.subscribe(lambda _evt: handler())

    def on_connected(self, handler):
        return self._connected.subscribe(handler)

    def on_disconnected(self, handler):
        return self._disconnected.subscribe(handler)

    # test drivers
    def fire_btn_mode(self):
        self._btn_mode.emit(BtnModePressed())

    def fire_connected(self):
        self._connected.emit(GamepadConnected())

    def fire_disconnected(self):
        self._disconnected.emit(GamepadDisconnected())


class FakeOverlay:
    """HomeMenuOverlay port — records the lifecycle the controller drives."""

    def __init__(self):
        self.shown_with = None
        self._showing = False
        self.closed_handler = None
        self.disposed = False

    def show_overlay(self, items, on_select=None, on_cancel=None):
        self.shown_with = (items, on_select, on_cancel)
        self._showing = True

    def hide_overlay(self):
        self._showing = False

    def is_showing(self):
        return self._showing

    def on_closed(self, handler):
        self.closed_handler = handler
        return lambda: None

    def dispose(self):
        self.disposed = True


class FakeOverlayFactory:
    def __init__(self):
        self.created: list[FakeOverlay] = []

    def create_home_overlay(self):
        overlay = FakeOverlay()
        self.created.append(overlay)
        return overlay


class FakeDesktop:
    """Plays DesktopControl, SessionView and DesktopShell for the controller."""

    def __init__(self, current=None, foreground=None):
        self._current = current
        self._foreground = foreground
        self.restored: list = []
        self.closed: list = []
        self.show_desktop_calls = 0
        self.resumed = 0
        self.hidden = 0
        self.volume_opened = 0

    # DesktopControl
    def current_app(self):
        return self._current

    def restore_app(self, target):
        self.restored.append(target)

    def request_close_app(self, target):
        self.closed.append(target)

    def show_desktop(self):
        self.show_desktop_calls += 1

    def foreground_pid(self):
        return self._foreground

    def confirm(self, question, on_confirmed):
        on_confirmed()

    # SessionView
    def resume(self):
        self.resumed += 1

    def hide(self):
        self.hidden += 1

    # DesktopShell (system-action effects)
    def open_volume_overlay(self):
        self.volume_opened += 1

    def pause(self):
        pass


class FakeWM:
    def __init__(self):
        self.minimized: list = []
        self.raised: list = []

    def minimize_windows_for_pids(self, pids):
        self.minimized.append(pids)

    def raise_windows_for_pid_exact(self, pid):
        self.raised.append(pid)


class FakeTray:
    def __init__(self):
        self.states: list[bool] = []

    def set_connected(self, connected):
        self.states.append(connected)


class FakePower:
    def suspend(self): ...
    def reboot(self): ...
    def poweroff(self): ...


def make_app(desktop=None, gamepad=None, factory=None, tray=None, wm=None):
    desktop = desktop or FakeDesktop()
    gamepad = gamepad or FakeGamepad()
    factory = factory or FakeOverlayFactory()
    tray = tray or FakeTray()
    wm = wm or FakeWM()
    controller = Application(
        gamepad=gamepad,
        desktop=desktop,
        action_deps=ActionDeps(desktop=desktop, power=FakePower()),
        tray=tray,
        wm=wm,
        overlay_factory=factory,
    )
    return controller, desktop, gamepad, factory, tray, wm


# ── BTN_MODE → overlay lifecycle ─────────────────────────────────────────────

class TestBtnModeOverlay:
    def test_press_creates_and_shows_overlay(self):
        controller, _, gamepad, factory, _, _ = make_app()
        gamepad.fire_btn_mode()
        assert len(factory.created) == 1
        overlay = factory.created[0]
        assert overlay.is_showing()
        items, on_select, _ = overlay.shown_with
        assert on_select == controller._dispatch_home

    def test_second_press_while_showing_hides(self):
        _, _, gamepad, factory, _, _ = make_app()
        gamepad.fire_btn_mode()   # show
        gamepad.fire_btn_mode()   # toggle off
        assert len(factory.created) == 1
        assert not factory.created[0].is_showing()

    def test_press_after_hide_disposes_old_and_creates_fresh(self):
        _, _, gamepad, factory, _, _ = make_app()
        gamepad.fire_btn_mode()   # show #0
        gamepad.fire_btn_mode()   # hide #0
        gamepad.fire_btn_mode()   # fresh #1
        assert len(factory.created) == 2
        assert factory.created[0].disposed
        assert factory.created[1].is_showing()

    def test_cancel_restores_app_when_one_is_foreground(self):
        app = App(name="Steam", command="steam")
        desktop = FakeDesktop(current=app)
        _, desktop, gamepad, factory, _, _ = make_app(desktop=desktop)
        gamepad.fire_btn_mode()
        _, _, on_cancel = factory.created[0].shown_with
        assert on_cancel is not None
        on_cancel()
        assert desktop.restored == [app]

    def test_cancel_is_none_on_bare_desktop(self):
        _, _, gamepad, factory, _, _ = make_app(desktop=FakeDesktop(current=None))
        gamepad.fire_btn_mode()
        _, _, on_cancel = factory.created[0].shown_with
        assert on_cancel is None


# ── _dispatch_home routing ───────────────────────────────────────────────────

class TestDispatchHome:
    def test_return_to_app_restores(self):
        controller, desktop, *_ = make_app()
        target = App(name="X", command="x")
        controller._dispatch_home(MenuItem("X", RETURN_TO_APP, target=target))
        assert desktop.restored == [target]

    def test_close_app_requests_close(self):
        controller, desktop, *_ = make_app()
        target = App(name="X", command="x")
        controller._dispatch_home(MenuItem("X", CLOSE_APP, target=target))
        assert desktop.closed == [target]

    def test_return_to_desktop_from_bare_desktop_just_shows(self):
        controller, desktop, _, _, _, wm = make_app(desktop=FakeDesktop(current=None))
        controller._dispatch_home(MenuItem("D", RETURN_TO_DESKTOP))
        assert desktop.show_desktop_calls == 1
        assert wm.minimized == []   # nothing to leave

    def test_return_to_desktop_from_app_minimizes_and_raises(self):
        desktop = FakeDesktop(current=App(name="X", command="x"), foreground=4242)
        controller, desktop, _, _, _, wm = make_app(desktop=desktop)
        controller._dispatch_home(MenuItem("D", RETURN_TO_DESKTOP))
        assert wm.minimized == [{4242}]
        assert wm.raised      # raised KD by its own pid
        assert desktop.show_desktop_calls == 1

    def test_system_action_runs_effect(self):
        controller, desktop, *_ = make_app()
        controller._dispatch_home(MenuItem("Vol", VOLUME))
        assert desktop.volume_opened == 1


# ── connect / disconnect → session policy ────────────────────────────────────

class TestConnection:
    def test_connected_resumes_and_flags_tray(self):
        _, desktop, gamepad, _, tray, _ = make_app()
        gamepad.fire_connected()
        assert desktop.resumed == 1
        assert tray.states == [True]

    def test_disconnected_hides_and_flags_tray(self):
        _, desktop, gamepad, _, tray, _ = make_app()
        gamepad.fire_disconnected()
        assert desktop.hidden == 1
        assert tray.states == [False]

    def test_disconnect_dismisses_open_overlay(self):
        _, _, gamepad, factory, _, _ = make_app()
        gamepad.fire_btn_mode()             # overlay open
        gamepad.fire_disconnected()
        assert not factory.created[0].is_showing()


# ── shutdown ─────────────────────────────────────────────────────────────────

class TestShutdown:
    def test_unsubscribes_from_gamepad(self):
        controller, _, gamepad, factory, _, _ = make_app()
        controller.shutdown()
        gamepad.fire_btn_mode()
        assert factory.created == []   # no longer reacting

    def test_disposes_open_overlay(self):
        controller, _, gamepad, factory, _, _ = make_app()
        gamepad.fire_btn_mode()
        controller.shutdown()
        assert factory.created[0].disposed
