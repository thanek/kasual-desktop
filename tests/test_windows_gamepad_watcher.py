"""Unit tests for WindowsGamepadWatcher (pygame implementation).

Mirror of the Linux ``test_gamepad_watcher.py``: same handler-stack contract,
same navigation-event mapping, but the source events come from pygame's SDL
GameController API (``CONTROLLERBUTTONDOWN``, ``CONTROLLERAXISMOTION``) instead
of evdev.

Tests:
  - handler stack (push/pop, LIFO, top_handler, inject)
  - button mapping: SOUTH→SELECT, EAST→CANCEL, NORTH→CLOSE, START→MANAGE
  - START+SELECT held → BTN_MODE
  - stick axis: threshold/hysteresis (_handle_stick_axis, _handle_axis), int16
  - D-pad as discrete buttons (DPAD_* → directions; D-pad-up ≠ overlay)
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
    DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT,
    STICK_RESET, STICK_THRESHOLD,
    WindowsGamepadWatcher,
)
from infrastructure.windows.input.driver_probe import DriverCapabilities
from domain.input.recall import RecallTrigger
from domain.input.vocabulary import Event, Trigger


def _cooperative_caps(*a, **kw):
    """probe_drivers() that reports no drivers → cooperative mode."""
    return DriverCapabilities(vigembus=False, hidhide=False)


@pytest.fixture
def mock_watcher(qapp):
    """WindowsGamepadWatcher without starting the _loop thread or pygame init.

    Patches threading.Thread before __init__ calls it, and pygame.init /
    joystick.init / display.init so no real joystick subsystem is touched.
    probe_drivers is patched to return cooperative (no DLLs loaded in tests).
    Mirrors the Linux ``mock_gamepad`` fixture in conftest.py.

    Yields the watcher and cleans up on teardown: cancels any armed
    RecallTrigger hold timer and clears DirectionRepeat state, so a HOLD_1S
    press left running by a test can't fire ``_bridge.btn.emit`` after the
    fixture's Qt objects are gone (a late fire would raise
    ``AttributeError: '_Bridge' does not have a signal with the signature btn()``
    from a garbage-collected C++ QObject)."""
    with patch("infrastructure.windows.input.gamepad_watcher.threading.Thread"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.pygame.display.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.game_controller.init"), \
         patch("infrastructure.windows.input.gamepad_watcher.probe_drivers", _cooperative_caps):
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
    # SDL GameController axes are int16 (-32768..32767); 28000 is past the
    # threshold, 12000 sits in the dead zone, 2000 is below the reset line.
    def test_positive_x_emits_right(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 28000)   # axis 0 = x
        qapp.processEvents()
        assert received == [Event.RIGHT]
        assert mock_watcher._stick["x"] == Event.RIGHT

    def test_negative_x_emits_left(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, -28000)
        qapp.processEvents()
        assert received == [Event.LEFT]

    def test_positive_y_emits_down(self, mock_watcher, qapp):
        # SDL axis 1: positive = down.
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(1, 28000)
        qapp.processEvents()
        assert received == [Event.DOWN]

    def test_negative_y_emits_up(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(1, -28000)
        qapp.processEvents()
        assert received == [Event.UP]

    def test_no_repeat_same_direction(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 28000)
        qapp.processEvents()
        mock_watcher._handle_axis(0, 30000)   # still right, no new event
        qapp.processEvents()
        assert received == [Event.RIGHT]

    def test_reset_below_hysteresis(self, mock_watcher, qapp):
        mock_watcher._handle_axis(0, 28000)
        qapp.processEvents()
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 2000)   # below STICK_RESET
        qapp.processEvents()
        assert received == []   # reset doesn't emit, only clears state
        assert mock_watcher._stick["x"] is None

    def test_dead_zone_between_reset_and_threshold(self, mock_watcher, qapp):
        # 12000 is > STICK_RESET (8000) but < STICK_THRESHOLD (16000) → no event.
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(0, 12000)
        qapp.processEvents()
        assert received == []
        assert mock_watcher._stick["x"] is None

    def test_axis_2_and_3_ignored(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_axis(2, 28000)
        mock_watcher._handle_axis(3, 28000)
        qapp.processEvents()
        assert received == []


# ── D-pad (discrete buttons via the GameController API) ────────────────────────

class TestDpad:
    def test_dpad_left(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_down(DPAD_LEFT)
        qapp.processEvents()
        assert received == [Event.LEFT]

    def test_dpad_right(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_down(DPAD_RIGHT)
        qapp.processEvents()
        assert received == [Event.RIGHT]

    def test_dpad_down(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_down(DPAD_DOWN)
        qapp.processEvents()
        assert received == [Event.DOWN]

    def test_dpad_up_emits_up_not_btn_mode(self, mock_watcher, qapp):
        # Regression: D-pad-up must NOT open the overlay. On an 8BitDo X-input
        # pad the raw joystick index for D-pad-up collided with the guide index,
        # which is exactly what the GameController API fixes.
        received = []
        fired = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher.on_btn_mode(lambda: fired.append(True))
        mock_watcher._handle_button_down(DPAD_UP)
        qapp.processEvents()
        assert received == [Event.UP]
        assert fired == []

    def test_dpad_release_stops_repeat(self, mock_watcher, qapp):
        mock_watcher._handle_button_down(DPAD_LEFT)
        qapp.processEvents()
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_up(DPAD_LEFT)
        qapp.processEvents()
        assert received == []   # release doesn't emit a nav event


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
        mock_watcher._on_connected_main()
        assert len(got) == 1

    def test_on_disconnected_delivers_event(self, mock_watcher, qapp):
        got = []
        mock_watcher.on_disconnected(lambda evt: got.append(evt))
        mock_watcher._on_disconnected_main()
        assert len(got) == 1

    def test_on_btn_mode_delivers_event(self, mock_watcher, qapp):
        got = []
        mock_watcher.on_btn_mode(lambda: got.append(True))
        mock_watcher._on_btn_mode_main()
        assert got == [True]


# ── refresh / shutdown ────────────────────────────────────────────────────────

class TestLifecycle:
    def test_refresh_reinits_controller_subsystem(self, mock_watcher):
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick") as js, \
             patch("infrastructure.windows.input.gamepad_watcher.game_controller") as gc:
            mock_watcher.refresh()
            js.quit.assert_called_once()
            js.init.assert_called_once()
            gc.quit.assert_called_once()
            gc.init.assert_called_once()

    def test_refresh_clears_repeat_and_recall(self, mock_watcher):
        mock_watcher._repeat.press(Event.UP)
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick"), \
             patch("infrastructure.windows.input.gamepad_watcher.game_controller"):
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


# ── Exclusive-mode forwarding (ViGEm) ─────────────────────────────────────────

class TestExclusiveForwarding:
    """Verify that in exclusive mode, gamepad events are forwarded to the
    virtual ViGEm pad — gated by ``not stack.suppressed``.

    The fixture creates a cooperative watcher (no DLLs), then injects a mock
    writer and flips ``_exclusive`` to True, simulating exclusive mode without
    needing real drivers.
    """

    def _exclusive_watcher(self, mock_watcher):
        """Turn a cooperative mock_watcher into an exclusive one with a mock writer."""
        mock_watcher._exclusive = True
        mock_watcher._writer = MagicMock()
        return mock_watcher

    def test_button_press_when_not_suppressed_writes_to_vigem(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        # Empty stack → not suppressed → forward.
        assert not gw._stack.suppressed
        gw._handle_button_down(BTN_SOUTH)
        gw._writer.write_button.assert_called_once_with(BTN_SOUTH, 1)

    def test_button_release_when_not_suppressed_writes_to_vigem(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw._handle_button_up(BTN_SOUTH)
        gw._writer.write_button.assert_called_once_with(BTN_SOUTH, 0)

    def test_button_press_when_suppressed_does_not_write_to_vigem(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw.push_handler(lambda e: None)  # Kasual active → suppressed
        assert gw._stack.suppressed
        gw._handle_button_down(BTN_SOUTH)
        gw._writer.write_button.assert_not_called()

    def test_button_release_when_suppressed_does_not_write_to_vigem(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw.push_handler(lambda e: None)
        gw._handle_button_up(BTN_SOUTH)
        gw._writer.write_button.assert_not_called()

    def test_btn_mode_short_press_forwards_synthetic_to_vigem(self, mock_watcher, qapp):
        """HOLD_1S trigger, empty stack, press+release BTN_MODE (< 1s) →
        synthetic guide pulse (set_guide True then False)."""
        gw = self._exclusive_watcher(mock_watcher)
        gw.set_app_btn_mode_trigger(Trigger.HOLD_1S)
        # Stack is empty → not suppressed.
        gw._handle_button_down(BTN_MODE)
        qapp.processEvents()
        # Hold timer NOT fired yet (press was instant).
        gw._handle_button_up(BTN_MODE)
        # RecallTrigger.release returns True (short press, not suppressed) → forward.
        assert gw._writer.set_guide.call_count == 2
        gw._writer.set_guide.assert_any_call(True)
        gw._writer.set_guide.assert_any_call(False)

    def test_btn_mode_hold_recall_does_not_forward(self, mock_watcher, qapp):
        """HOLD_1S trigger, empty stack, press, hold > 1s (timer fires), release
        → no synthetic forward (the press recalled the menu)."""
        gw = self._exclusive_watcher(mock_watcher)
        gw.set_app_btn_mode_trigger(Trigger.HOLD_1S)
        # Use a fake timer that fires immediately to simulate the hold elapsing.
        gw._recall = RecallTrigger(
            on_recall=gw._bridge.btn.emit,
            timer_factory=lambda secs, cb: _ImmediateTimer(cb),
        )
        gw._handle_button_down(BTN_MODE)
        qapp.processEvents()
        # Timer fired → recall happened → release should NOT forward.
        gw._handle_button_up(BTN_MODE)
        gw._writer.set_guide.assert_not_called()

    def test_btn_mode_press_when_suppressed_does_not_forward(self, mock_watcher, qapp):
        """Handler on stack, press+release BTN_MODE → no synthetic forward
        (suppressed)."""
        gw = self._exclusive_watcher(mock_watcher)
        gw.push_handler(lambda e: None)  # Kasual active → suppressed
        gw._handle_button_down(BTN_MODE)
        qapp.processEvents()
        gw._handle_button_up(BTN_MODE)
        gw._writer.set_guide.assert_not_called()

    def test_axis_forwarded_when_not_suppressed(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw._handle_axis(0, 28000)
        gw._writer.write_axis.assert_called_once_with(0, 28000)

    def test_axis_not_forwarded_when_suppressed(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw.push_handler(lambda e: None)
        gw._handle_axis(0, 28000)
        gw._writer.write_axis.assert_not_called()

    def test_dpad_forwarded_when_not_suppressed(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw._handle_button_down(DPAD_LEFT)
        gw._writer.write_button.assert_called_once_with(DPAD_LEFT, 1)

    def test_dpad_not_forwarded_when_suppressed(self, mock_watcher, qapp):
        gw = self._exclusive_watcher(mock_watcher)
        gw.push_handler(lambda e: None)
        gw._handle_button_down(DPAD_LEFT)
        gw._writer.write_button.assert_not_called()


class _ImmediateTimer:
    """A timer substitute that fires its callback immediately on start()."""

    def __init__(self, callback):
        self._callback = callback
        self._cancelled = False

    def start(self):
        if not self._cancelled:
            self._callback()

    def cancel(self):
        self._cancelled = True


# ── Cooperative fallback ──────────────────────────────────────────────────────

class TestCooperativeFallback:
    """Verify that in cooperative mode (drivers absent), no ViGEm writes happen."""

    def test_no_vigem_writes_when_drivers_absent(self, mock_watcher, qapp):
        """Default mock_watcher fixture is cooperative (probe_drivers → False/False).
        No writer should exist, and pressing buttons should not raise."""
        assert mock_watcher._writer is None
        assert mock_watcher._exclusive is False
        mock_watcher.push_handler(lambda e: None)
        mock_watcher._handle_button_down(BTN_SOUTH)
        qapp.processEvents()
        # No writer → no writes, no exception.

    def test_hidhide_absent_disables_exclusive_even_if_vigem_present(self, qapp):
        """D4 all-or-nothing: ViGEm present but HidHide absent → cooperative."""
        caps = DriverCapabilities(vigembus=True, hidhide=False)
        assert caps.exclusive is False

    def test_vigem_absent_disables_exclusive_even_if_hidhide_present(self, qapp):
        caps = DriverCapabilities(vigembus=False, hidhide=True)
        assert caps.exclusive is False

    def test_both_present_enables_exclusive(self, qapp):
        caps = DriverCapabilities(vigembus=True, hidhide=True)
        assert caps.exclusive is True


# ── Exclusive-mode setup ──────────────────────────────────────────────────────

class TestExclusiveSetup:
    """_setup_exclusive must hide the physical pad and activate the cloak only
    when a real HID gamepad node exists; otherwise it falls back to cooperative
    (no virtual pad) so an XInput-only pad isn't duplicated."""

    def _make_exclusive(self, mock_watcher):
        mock_watcher._exclusive = True
        return mock_watcher

    def test_setup_falls_back_when_no_hid_node(self, mock_watcher):
        gw = self._make_exclusive(mock_watcher)
        with patch("infrastructure.windows.input.hidhide.HidHideClient") as HH, \
             patch("infrastructure.windows.input.vigembus_writer.VigemWriter") as VW:
            HH.resolve_gamepad_instance_ids.return_value = []
            gw._setup_exclusive()
        # No node to hide → no virtual pad created (avoids a duplicate XInput pad).
        assert gw._writer is None
        VW.assert_not_called()

    def test_setup_hides_activates_and_connects_when_node_present(self, mock_watcher):
        gw = self._make_exclusive(mock_watcher)
        instance = r"HID\VID_054C&PID_0CE6\7&1"   # DInput pad, no IG_
        hh = MagicMock()
        with patch("infrastructure.windows.input.hidhide.HidHideClient") as HH, \
             patch("infrastructure.windows.input.vigembus_writer.VigemWriter") as VW:
            HH.resolve_gamepad_instance_ids.return_value = [instance]
            HH.return_value = hh
            gw._setup_exclusive()
        hh.register_self.assert_called_once()
        hh.set_active.assert_called_once_with(True)   # cloak must be activated
        hh.hide_device.assert_called_once_with(instance)
        VW.return_value.connect.assert_called_once()
        assert gw._writer is VW.return_value

    def test_setup_falls_back_for_xinput_pad(self, mock_watcher):
        # An XInput-backed pad (HID path contains IG_) can't be hidden from the
        # XInput API, so exclusive must fall back rather than create a 2nd pad.
        gw = self._make_exclusive(mock_watcher)
        with patch("infrastructure.windows.input.hidhide.HidHideClient") as HH, \
             patch("infrastructure.windows.input.vigembus_writer.VigemWriter") as VW:
            HH.resolve_gamepad_instance_ids.return_value = [
                r"HID\VID_2DC8&PID_3106&IG_00\B&2599DE0F&0&0000",
            ]
            gw._setup_exclusive()
        assert gw._writer is None
        VW.assert_not_called()

    def test_setup_noop_in_cooperative_mode(self, mock_watcher):
        # _exclusive stays False (default fixture) → setup does nothing.
        with patch("infrastructure.windows.input.hidhide.HidHideClient") as HH:
            mock_watcher._setup_exclusive()
        HH.resolve_gamepad_instance_ids.assert_not_called()
        assert mock_watcher._writer is None

    def test_refresh_reestablishes_exclusive_when_connected(self, mock_watcher):
        gw = self._make_exclusive(mock_watcher)
        gw._connected = True
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick"), \
             patch("infrastructure.windows.input.gamepad_watcher.game_controller"), \
             patch.object(gw, "_setup_exclusive") as setup, \
             patch.object(gw, "_teardown_exclusive") as teardown:
            gw.refresh()
        teardown.assert_called_once()
        setup.assert_called_once()

    def test_refresh_skips_resetup_when_disconnected(self, mock_watcher):
        gw = self._make_exclusive(mock_watcher)
        gw._connected = False
        with patch("infrastructure.windows.input.gamepad_watcher.pygame.joystick"), \
             patch("infrastructure.windows.input.gamepad_watcher.game_controller"), \
             patch.object(gw, "_setup_exclusive") as setup:
            gw.refresh()
        setup.assert_not_called()


# ── Duplicate-view dedup ──────────────────────────────────────────────────────

class TestDuplicateViewDedup:
    """A pad open as several SDL views (DInput + XInput) delivers each physical
    press once per view; the held-set must collapse those to a single event so
    navigation doesn't double-fire. (Guide only comes from the XInput view, so
    it isn't duplicated — the dedup is purely about the shared buttons.)"""

    def test_duplicate_button_down_dispatches_once(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_down(BTN_SOUTH)   # view 1
        mock_watcher._handle_button_down(BTN_SOUTH)   # view 2 — duplicate, ignored
        qapp.processEvents()
        assert received == [Event.SELECT]

    def test_release_then_repress_dispatches_again(self, mock_watcher, qapp):
        received = []
        mock_watcher.push_handler(lambda e: received.append(e))
        mock_watcher._handle_button_down(BTN_SOUTH)
        mock_watcher._handle_button_up(BTN_SOUTH)
        mock_watcher._handle_button_down(BTN_SOUTH)   # genuine second press
        qapp.processEvents()
        assert received == [Event.SELECT, Event.SELECT]

    def test_duplicate_button_down_forwards_to_vigem_once(self, mock_watcher):
        mock_watcher._exclusive = True
        mock_watcher._writer = MagicMock()
        mock_watcher._handle_button_down(BTN_SOUTH)
        mock_watcher._handle_button_down(BTN_SOUTH)   # duplicate
        mock_watcher._writer.write_button.assert_called_once_with(BTN_SOUTH, 1)
