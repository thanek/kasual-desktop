"""
Windows gamepad implementation using pygame.

Cooperative model: ALL apps see gamepad events simultaneously.
There is no exclusive grab on Windows without a kernel driver.

BTN_MODE handling: On Windows, BTN_MODE always triggers HomeOverlay
(because we can't intercept it without grab). This is a design
decision - the Windows shell takeover model means we're the only
active shell anyway.

Uses JOY* events (joystick API) which work with most controllers
including 8BitDo, Xbox, PlayStation (via XInput).

The shared `PadControl` / `GamepadSignals` plumbing — the handler stack, the
observer emitters and the background-thread → GUI-thread hops — lives in
:class:`BaseGamepadWatcher`; this adapter adds only the pygame read loop.
"""

import logging
import threading

import pygame

from domain.input.direction_repeat import DirectionRepeat
from domain.input.recall import RecallTrigger
from domain.input.vocabulary import Event, Trigger
from infrastructure.common.input.gamepad_watcher_base import BaseGamepadWatcher

logger = logging.getLogger(__name__)

STICK_THRESHOLD = 0.5
STICK_RESET = 0.1

# Triggers (LT/RT) are analog. SDL/XInput reports them on axes 4/5; resting value
# differs by backend (−1.0 or 0.0), so RESET sits just above 0.0 to relax under
# either convention, and one VOLUME event fires per pull past THRESHOLD.
TRIGGER_THRESHOLD = 0.5
TRIGGER_RESET = 0.1
AXIS_LT = 4
AXIS_RT = 5

# Standard XInput/SDL button indices (verified on an 8BitDo Ultimate in X-input
# mode). The previous values had Start/Select on the bumpers and X/Y swapped.
BTN_SOUTH = 0    # A
BTN_EAST = 1     # B
BTN_WEST = 2     # X
BTN_NORTH = 3    # Y
BTN_TL = 4       # LB
BTN_TR = 5       # RB
BTN_SELECT = 6   # Back / View
BTN_START = 7    # Start / Menu
BTN_MODE = 10    # Guide / Home

HAT_CENTER = 0
HAT_UP = 1
HAT_RIGHT = 2
HAT_DOWN = 3
HAT_LEFT = 4


class WindowsGamepadWatcher(BaseGamepadWatcher):
    """Reads events from a gamepad using pygame in a background thread.

    On Windows, gamepads are cooperative — all applications see all events. We
    don't use grab() because Windows doesn't support it without a kernel driver,
    so events are surfaced via the base's GUI-thread hops but never intercepted.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._joystick = None

        # BTN_MODE recall policy: per the foreground app's trigger, a quick guide
        # press is left to the app (e.g. Steam's own menu — the controller is
        # cooperative on Windows, so Steam sees it natively) and only a ~1 s HOLD
        # opens the Kasual menu. When Kasual itself is in control (a handler on the
        # stack) recall is always immediate. The hold timer fires on_recall on a
        # background thread; the base's btn-mode hop marshals it to the GUI thread.
        self._app_trigger = Trigger.CLICK
        self._recall = RecallTrigger(on_recall=self._hop_btn_mode)

        pygame.init()
        pygame.joystick.init()
        pygame.display.init()

        self._held = set()
        self._stick = {"x": None, "y": None}
        self._hat_state = {"x": None, "y": None}
        self._trigger = {"lt": None, "rt": None}   # latched analog-trigger state
        # Auto-fire: a held direction re-emits like a keyboard key-repeat. Pure
        # timing policy lives in the domain; the loop polls due() each tick (the
        # 60 fps tick is well under the repeat interval, so none are missed).
        self._repeat = DirectionRepeat()

        self._thread = threading.Thread(target=self._loop, daemon=True, name="windows-gamepad-watcher")
        self._thread.start()

        logger.info("WindowsGamepadWatcher started")

    def _loop(self):
        """Main event reading loop."""
        clock = pygame.time.Clock()
        # Loop-thread connection guard (dedupe duplicate device events). The
        # base's `self._connected` is GUI-thread-owned for late-subscriber
        # replay, so it must not be read here — the hop only flips it later.
        was_connected = False

        while self._running:
            clock.tick(60)

            try:
                events = pygame.event.get()
            except Exception as e:
                logger.warning("Error getting pygame events: %s", e)
                continue

            for event in events:
                if event.type == pygame.JOYDEVICEADDED:
                    joy_id = event.device_index
                    logger.info("Gamepad connected: %d", joy_id)
                    if not was_connected:
                        was_connected = True
                        self._joystick = pygame.joystick.Joystick(joy_id)
                        self._joystick.init()
                        logger.info("Joystick initialized: %s", self._joystick.get_name())
                        self._hop_connected()

                elif event.type == pygame.JOYDEVICEREMOVED:
                    logger.info("Gamepad disconnected")
                    if was_connected:
                        was_connected = False
                        self._joystick = None
                        self._repeat.clear()
                        self._recall.cancel()
                        self._stick = {"x": None, "y": None}
                        self._hat_state = {"x": None, "y": None}
                        self._trigger = {"lt": None, "rt": None}
                        self._hop_disconnected()

                elif event.type == pygame.JOYBUTTONDOWN:
                    self._handle_button_down(event.button)

                elif event.type == pygame.JOYBUTTONUP:
                    self._handle_button_up(event.button)

                elif event.type == pygame.JOYAXISMOTION:
                    self._handle_axis(event.axis, event.value)

                elif event.type == pygame.JOYHATMOTION:
                    self._handle_hat(event.hat, event.value)

            # Re-emit the held direction when its next auto-repeat is due.
            repeated = self._repeat.due()
            if repeated is not None:
                self._hop_nav(repeated)

    def _handle_button_down(self, button: int):
        """Handle button press."""
        self._held.add(button)
        logger.debug("Button down: %d", button)

        if button == BTN_MODE:
            # CLICK / Kasual active → recall now; HOLD_1S app → arm the hold.
            self._recall.press(kasual_active=bool(self._stack), trigger=self._app_trigger)
        elif button == BTN_SOUTH:
            self._hop_nav(Event.SELECT)
        elif button == BTN_EAST:
            self._hop_nav(Event.CANCEL)
        elif button == BTN_WEST:
            self._hop_nav(Event.CLOSE)
        elif button == BTN_TL:
            self._hop_nav(Event.SECTION_PREV)
        elif button == BTN_TR:
            self._hop_nav(Event.SECTION_NEXT)
        elif button == BTN_START:
            if BTN_SELECT in self._held:
                self._hop_btn_mode()
            else:
                self._hop_nav(Event.MANAGE)

    def _handle_button_up(self, button: int):
        """Handle button release."""
        self._held.discard(button)
        if button == BTN_MODE:
            # Cancels a pending hold. The short-press "forward to the app" the
            # return value reports is moot on Windows — the controller is
            # cooperative, so the app already saw the guide press itself.
            self._recall.release(suppressed=bool(self._stack))

    def _handle_axis(self, axis: int, value: float):
        """Handle analog stick movement."""
        if axis == 0:
            self._handle_stick_axis("x", value, Event.LEFT, Event.RIGHT)
        elif axis == 1:
            self._handle_stick_axis("y", value, Event.UP, Event.DOWN)
        elif axis == AXIS_LT:
            self._handle_trigger_axis("lt", value, Event.VOLUME_DOWN)
        elif axis == AXIS_RT:
            self._handle_trigger_axis("rt", value, Event.VOLUME_UP)

    def _handle_stick_axis(self, axis: str, value: float, neg_event: str, pos_event: str):
        """Handle stick axis with threshold and hysteresis."""
        if value < -STICK_THRESHOLD and self._stick[axis] != neg_event:
            self._stick[axis] = neg_event
            self._hop_nav(neg_event)
            self._repeat.press(neg_event)
        elif value > STICK_THRESHOLD and self._stick[axis] != pos_event:
            self._stick[axis] = pos_event
            self._hop_nav(pos_event)
            self._repeat.press(pos_event)
        elif abs(value) < STICK_RESET:
            if self._stick[axis] is not None:
                self._repeat.release(self._stick[axis])
            self._stick[axis] = None

    def _handle_trigger_axis(self, key: str, value: float, event: str):
        """Fire one volume event per trigger pull past THRESHOLD (no auto-repeat).

        ``self._trigger[key]`` latches so a held trigger emits once and only
        re-fires after relaxing below TRIGGER_RESET — mirrors the stick's
        hysteresis but for a discrete "nudge volume" gesture."""
        if value > TRIGGER_THRESHOLD and self._trigger[key] != event:
            self._trigger[key] = event
            self._hop_nav(event)
        elif value < TRIGGER_RESET:
            self._trigger[key] = None

    def _handle_hat(self, hat: int, value: tuple[int, int]):
        """Handle D-pad (hat) movement."""
        if hat != 0:
            return

        x, y = value
        logger.debug("Hat motion: hat=%d, x=%d, y=%d", hat, x, y)
        new_x = None
        new_y = None

        if x == -1:
            new_x = Event.LEFT
        elif x == 1:
            new_x = Event.RIGHT

        if y == -1:
            new_y = Event.DOWN
        elif y == 1:
            new_y = Event.UP

        if new_x and self._hat_state["x"] != new_x:
            self._hat_state["x"] = new_x
            self._hop_nav(new_x)
            self._repeat.press(new_x)
        elif x == 0 and self._hat_state["x"] is not None:
            self._repeat.release(self._hat_state["x"])
            self._hat_state["x"] = None

        if new_y and self._hat_state["y"] != new_y:
            self._hat_state["y"] = new_y
            self._hop_nav(new_y)
            self._repeat.press(new_y)
        elif y == 0 and self._hat_state["y"] is not None:
            self._repeat.release(self._hat_state["y"])
            self._hat_state["y"] = None

    def set_app_btn_mode_trigger(self, trigger: str) -> None:
        """Set how BTN_MODE recalls the Kasual menu for the current foreground:
        ``Trigger.CLICK`` (immediate) or ``Trigger.HOLD_1S`` (require a ~1 s hold,
        leaving a quick press to the app). Driven by AppLifecycle as apps come and
        go; the trigger stays put for a whole app session (so a launcher's child
        games inherit it) until the Desktop is reactivated (reset to CLICK)."""
        self._app_trigger = trigger

    def refresh(self) -> None:
        """Reinitialize joystick subsystem."""
        self._repeat.clear()
        self._recall.cancel()
        pygame.joystick.quit()
        pygame.joystick.init()

    def shutdown(self):
        """Stop the watcher thread."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        pygame.quit()
