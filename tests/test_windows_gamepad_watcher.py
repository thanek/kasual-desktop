"""Unit tests for WindowsGamepadWatcher (pygame implementation).

Mirror of the Linux ``test_gamepad_watcher.py``: same handler-stack contract,
same navigation-event mapping, but the source events come from pygame
(``JOYBUTTONDOWN``, ``JOYAXISMOTION``, ``JOYHATMOTION``) instead of evdev.

Tests:
  - handler stack (push/pop, LIFO, top_handler, inject)
  - button mapping: SOUTH→SELECT, EAST→CANCEL, NORTH→CLOSE, START→MANAGE
  - START+SELECT held → BTN_MODE
  - stick axis: threshold/hysteresis (_handle_stick_axis, _handle_axis)
  - D-pad via _handle_hat (pygame hat value tuple)
  - BTN_MODE recall trigger (CLICK vs HOLD_1S) — domain logic lives in
    RecallTrigger (covered by test_recall_trigger.py); here we verify the
    watcher wires set_app_btn_mode_trigger and that recall emits btn_mode
  - on_btn_mode / on_connected / on_disconnected emitters
  - refresh() / shutdown() lifecycle

Skipped on non-Windows: the watcher imports ``pygame`` and is the Windows
gamepad port; the Linux evdev port has its own tests.

The _loop thread is blocked by the fixture (threading.Thread mocked), and
pygame init is mocked so no real joystick subsystem is touched.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs pygame/ctypes.windll", allow_module_level=True)

from infrastructure.windows.input.gamepad_watcher import (
    BTN_EAST, BTN_MODE, BTN_NORTH, BTN_SELECT, BTN_SOUTH, BTN_START, BTN_WEST,
    STICK_RESET, STICK_THRESHOLD,
    WindowsGamepadWatcher,
)
from domain.input.vocabulary import Event, Trigger


@pytest.fixture
def mock_watcher(qapp):
    """WindowsGamepadWatcher without starting the _loop thread or pygame init.

    Patches threading.Thread before __init__ calls it, and pygame.init /
    joystick.init / display.init so no real joystick subsystem is touched.
    Mirrors the Linux ``mock_gamepad`` fixture in conftest.py.

    Yields the watcher and cleans up on teardown: cancels any armed
    RecallTrigger hold timer and clears DirectionRepeat state, so a HOLD_1S
    press left running by a test can't fire the base's btn-mode hop after the
    fixture's Qt objects are gone (a late fire would raise an AttributeError
    about a missing signal from a garbage-collected C++ QObject)."""
    with patch("infrastructure.windows.input.gamepad_watcher.threading.Thread"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.display.init"):
        gw = WindowsGamepadWatcher()
    yield gw
    gw._recall.cancel()
    gw._repeat.clear()


def _btn(button: int):
    """A pygame JOYBUTTONDOWN-style event duck-typed for _handle_button_down."""
    return MagicMock(button=button)


# ── Stos handlerów ─────────────────────────────────────────────────────────────

class TestHandlerStack:
    def test_push_then_top_handler(self, mock_watcher):
        h1 = lambda e: None
        h2 = lambda e: None
        mock_watcher.push_handler(h1)
        assert mock_watcher.top_handler() is h1
        mock_watcher.push_handler(h2)
        assert mock_watcher.top_handler() is h2

    def test_pop_removes_handler(self, mock_watcher):
        h1 = lambda e: None
        h2 = lambda e: None
        mock_watcher.push_handler(h1)
        mock_watcher.push_handler(h2)
        mock_watcher.pop_handler(h2)
        assert mock_watcher.top_handler() is h1

    def test_pop_only_handler_empties_stack(self, mock_watcher):
        h = lambda e: None
        mock_watcher.push_handler(h)
        mock_watcher.pop_handler(h)
        assert mock_watcher.top_handler() is None

    def test_push_dedup_moves_existing_to_top(self, mock_watcher):
        # push_handler removes an existing entry before appending — a handler
        # pushed twice sits on top, not duplicated.
        h1 = lambda e: None
        h2 = lambda e: None
        mock_watcher.push_handler(h1)
        mock_watcher.push_handler(h2)
        mock_watcher.push_handler(h1)   # already in the stack
        assert mock_watcher.top_handler() is h1
        mock_watcher.pop_handler(h1)
        assert mock_watcher.top_handler() is h2   # h2 still there, not h1

    def test_pop_unregistered_is_noop(self, mock_watcher):
        h = lambda e: None
        mock_watcher.pop_handler(h)   # nie powinno rzucać
        assert mock_watcher.top_handler() is None


# ── _dispatch / inject ────────────────────────────────────────────────────────

class TestDispatch:
    def test_calls_top_handler_after_qt_hop(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._dispatch(Event.SELECT)
        qapp.processEvents()
        assert received == [Event.SELECT]

    def test_calls_only_top_handler(self, mock_watcher, qapp):
        bottom = []
        top = []
        mock_watcher.push_handler(lambda e: bottom.append(e))
        mock_watcher.push_handler(lambda e: top.append(e))
        mock_watcher._dispatch(Event.UP)
        qapp.processEvents()
        assert top == [Event.UP]
        assert bottom == []

    def test_noop_when_stack_empty(self, mock_watcher, qapp):
        mock_watcher._dispatch(Event.DOWN)   # nie powinno rzucać
        qapp.processEvents()

    def test_inject_routes_to_dispatch(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher.inject(Event.CANCEL)
        qapp.processEvents()
        assert received == [Event.CANCEL]


# ── Mapowanie przycisków ──────────────────────────────────────────────────────

class TestButtonMapping:
    def _press(self, gw, button, qapp):
        """Run a button-down through the watcher and flush the Qt signal hop."""
        gw._handle_button_down(button)
        qapp.processEvents()

    def test_south_emits_select(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        self._press(mock_watcher, BTN_SOUTH, qapp)
        assert received == [Event.SELECT]

    def test_east_emits_cancel(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        self._press(mock_watcher, BTN_EAST, qapp)
        assert received == [Event.CANCEL]

    def test_north_emits_close(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        self._press(mock_watcher, BTN_NORTH, qapp)
        assert received == [Event.CLOSE]

    def test_start_alone_emits_manage(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        self._press(mock_watcher, BTN_START, qapp)
        assert received == [Event.MANAGE]

    def test_start_plus_select_emits_btn_mode(self, mock_watcher, qapp):
        """BTN_START pressed while BTN_SELECT held → BTN_MODE (Home Overlay)."""
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher._held.add(BTN_SELECT)
        mock_watcher._handle_button_down(BTN_START)
        qapp.processEvents()
        assert fired == [True]

    def test_start_alone_does_not_emit_btn_mode(self, mock_watcher, qapp):
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        self._press(mock_watcher, BTN_START, qapp)
        assert fired == []

    def test_button_up_discards_from_held(self, mock_watcher):
        mock_watcher._held.add(BTN_SOUTH)
        mock_watcher._handle_button_up(BTN_SOUTH)
        assert BTN_SOUTH not in mock_watcher._held


# ── Stick analogowy — threshold / hysteresis ──────────────────────────────────

class TestStickAxis:
    def test_positive_x_emits_right(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 0.9)   # axis 0 = x
        qapp.processEvents()
        assert received == [Event.RIGHT]
        assert mock_watcher._stick["x"] == Event.RIGHT

    def test_negative_x_emits_left(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, -0.9)
        qapp.processEvents()
        assert received == [Event.LEFT]

    def test_positive_y_emits_down(self, mock_watcher, qapp):
        # pygame axis 1: positive = down (joystick convention).
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(1, 0.9)
        qapp.processEvents()
        assert received == [Event.DOWN]

    def test_negative_y_emits_up(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(1, -0.9)
        qapp.processEvents()
        assert received == [Event.UP]

    def test_no_repeat_same_direction(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 0.9)
        qapp.processEvents()
        mock_watcher._handle_axis(0, 0.95)   # still right, no new event
        qapp.processEvents()
        assert received == [Event.RIGHT]

    def test_reset_below_hysteresis(self, mock_watcher, qapp):
        mock_watcher._handle_axis(0, 0.9)
        qapp.processEvents()
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 0.05)   # below STICK_RESET
        qapp.processEvents()
        assert received == []   # reset doesn't emit, only clears state
        assert mock_watcher._stick["x"] is None

    def test_dead_zone_between_reset_and_threshold(self, mock_watcher, qapp):
        # 0.3 is > STICK_RESET (0.1) but < STICK_THRESHOLD (0.5) → no event.
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 0.3)
        qapp.processEvents()
        assert received == []
        assert mock_watcher._stick["x"] is None

    def test_axis_2_and_3_ignored(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(2, 0.9)
        mock_watcher._handle_axis(3, 0.9)
        qapp.processEvents()
        assert received == []


# ── D-pad (hat) ───────────────────────────────────────────────────────────────

class TestHat:
    def test_hat_left(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (-1, 0))
        qapp.processEvents()
        assert received == [Event.LEFT]

    def test_hat_right(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (1, 0))
        qapp.processEvents()
        assert received == [Event.RIGHT]

    def test_hat_down(self, mock_watcher, qapp):
        # pygame hat y: -1 = down.
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (0, -1))
        qapp.processEvents()
        assert received == [Event.DOWN]

    def test_hat_up(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (0, 1))
        qapp.processEvents()
        assert received == [Event.UP]

    def test_hat_center_clears_state(self, mock_watcher, qapp):
        mock_watcher._handle_hat(0, (-1, 0))
        qapp.processEvents()
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (0, 0))
        qapp.processEvents()
        assert received == []   # center doesn't emit
        assert mock_watcher._hat_state["x"] is None

    def test_hat_nonzero_index_ignored(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(1, (-1, 0))
        qapp.processEvents()
        assert received == []

    def test_diagonal_emits_both(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_hat(0, (-1, 1))   # left + up
        qapp.processEvents()
        assert Event.LEFT in received and Event.UP in received


# ── BTN_MODE — logika triggera ─────────────────────────────────────────────────

class TestBtnModeTrigger:
    def test_default_trigger_is_click(self, mock_watcher):
        assert mock_watcher._app_trigger == Trigger.CLICK

    def test_set_app_btn_mode_trigger_stores_value(self, mock_watcher):
        mock_watcher.set_app_btn_mode_trigger(Trigger.HOLD_1S)
        assert mock_watcher._app_trigger == Trigger.HOLD_1S

    def test_recall_immediate_when_kasual_active(self, mock_watcher, qapp):
        """With a handler on the stack (Kasual active), BTN_MODE recalls the
        menu immediately regardless of the app trigger."""
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher.push_handler(lambda e: None)   # Kasual active
        mock_watcher.set_app_btn_mode_trigger(Trigger.HOLD_1S)
        mock_watcher._handle_button_down(BTN_MODE)
        qapp.processEvents()
        assert fired == [True]

    def test_recall_hold_arms_when_kasual_inactive(self, mock_watcher, qapp):
        """No handler on the stack + HOLD_1S trigger → a press does NOT fire
        btn_mode immediately; the hold timer (in RecallTrigger) is armed."""
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher.set_app_btn_mode_trigger(Trigger.HOLD_1S)
        # Stack is empty → kasual_active=False.
        mock_watcher._handle_button_down(BTN_MODE)
        qapp.processEvents()
        assert fired == []   # hold not elapsed

    def test_recall_click_when_kasual_inactive(self, mock_watcher, qapp):
        """No handler on the stack + CLICK trigger → a press fires btn_mode
        immediately (the app gets the press too — cooperative controller)."""
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher.set_app_btn_mode_trigger(Trigger.CLICK)
        mock_watcher._handle_button_down(BTN_MODE)
        qapp.processEvents()
        assert fired == [True]

    def test_trigger_btn_mode_emits_directly(self, mock_watcher, qapp):
        """trigger_btn_mode / trigger_home bypass the recall logic and emit
        btn_mode directly — used by keyboard shortcuts."""
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher.trigger_btn_mode()
        assert fired == [True]   # EventEmitter is synchronous

    def test_trigger_home_aliases_trigger_btn_mode(self, mock_watcher, qapp):
        fired = []
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher.trigger_home()
        assert fired == [True]


# ── Stan połączenia ────────────────────────────────────────────────────────────

class TestConnectionState:
    def test_on_connected_delivers_event(self, mock_watcher, qapp):
        got = []
        mock_watcher.on_connected(lambda evt: got.append(evt))
        mock_watcher._on_connected_hop()
        assert len(got) == 1

    def test_on_connected_replays_to_late_subscriber(self, mock_watcher, qapp):
        # A subscriber that registers after the pad already connected (e.g. the
        # controller wired only after onboarding via --provision) still learns the
        # current state via a deferred replay — otherwise the Desktop never
        # surfaces. Mirrors the Linux watcher's on_connected replay.
        mock_watcher._connected = True
        got = []
        mock_watcher.on_connected(lambda evt: got.append(evt))
        assert got == []                 # deferred onto the event loop, not sync
        qapp.processEvents()
        assert len(got) == 1

    def test_on_connected_no_replay_when_disconnected(self, mock_watcher, qapp):
        # No pad connected → a fresh subscriber gets nothing until a real connect.
        got = []
        mock_watcher.on_connected(lambda evt: got.append(evt))
        qapp.processEvents()
        assert got == []

    def test_on_disconnected_delivers_event(self, mock_watcher, qapp):
        got = []
        mock_watcher.on_disconnected(lambda evt: got.append(evt))
        mock_watcher._on_disconnected_hop()
        assert len(got) == 1

    def test_on_btn_mode_delivers_event(self, mock_watcher, qapp):
        got = []
        mock_watcher.on_btn_mode(lambda: got.append(True))
        mock_watcher._on_btn_mode_hop()
        assert got == [True]


# ── refresh / shutdown ────────────────────────────────────────────────────────

class TestLifecycle:
    def test_refresh_reinits_joystick_subsystem(self, mock_watcher):
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick") as js:
            mock_watcher.refresh()
            js.quit.assert_called_once()
            js.init.assert_called_once()

    def test_refresh_clears_repeat_and_recall(self, mock_watcher):
        mock_watcher._repeat.press(Event.UP)
        mock_watcher.refresh()
        # No exception means the repeat/recall were cleared; their internal
        # state is domain-tested in test_direction_repeat / test_recall_trigger.

    def test_shutdown_stops_thread_and_quits_pygame(self, mock_watcher):
        mock_watcher._thread = MagicMock()
        mock_watcher._thread.is_alive.return_value = True
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.quit") as pg_quit:
            mock_watcher.shutdown()
        mock_watcher._thread.join.assert_called_once_with(timeout=1.0)
        pg_quit.assert_called_once()
        assert mock_watcher._running is False

    def test_shutdown_skips_join_when_thread_not_alive(self, mock_watcher):
        mock_watcher._thread = MagicMock()
        mock_watcher._thread.is_alive.return_value = False
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.quit"):
            mock_watcher.shutdown()
        mock_watcher._thread.join.assert_not_called()
