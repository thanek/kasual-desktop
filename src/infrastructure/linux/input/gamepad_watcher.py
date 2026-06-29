import logging
import select
import threading
import time

from PyQt6.QtCore import QObject
from evdev import InputDevice, InputEvent, UInput, ecodes, list_devices

from domain.input.direction_repeat import DirectionRepeat
from domain.input.recall import RecallTrigger
from domain.input.vocabulary import Event, Trigger
from infrastructure.common.input.gamepad_watcher_base import BaseGamepadWatcher

logger = logging.getLogger(__name__)

STICK_THRESHOLD = 10000   # analog axis range: -32768..32767
STICK_RESET     = 6000    # hysteresis — below this value the axis is "centered"

# Triggers (ABS_Z / ABS_RZ) are analog and rest at 0 (typical range 0..255), so
# they need the same threshold + hysteresis as the stick to fire once per pull
# instead of streaming a value every frame. A single VOLUME_DOWN/UP is emitted on
# the crossing; the axis must fall back below TRIGGER_RESET before it can re-fire.
TRIGGER_THRESHOLD = 150
TRIGGER_RESET     = 50

VIRTUAL_DEVICE_NAME   = "kasual-vpad"


class GamepadWatcher(BaseGamepadWatcher):
    """Reads events from a physical gamepad (evdev) in a background thread.

    The shared `PadControl` / `GamepadSignals` plumbing lives in
    :class:`BaseGamepadWatcher`; this adapter adds the Linux device handling.

    The gamepad is always grabbed exclusively. All events except BTN_MODE are
    forwarded to a virtual gamepad (UInput, name: VIRTUAL_DEVICE_NAME), which
    external applications (e.g. Steam) consume. Navigation events are translated
    and surfaced via the base's GUI-thread hops; BTN_MODE is observed separately
    (not forwarded to the stack or virtual gamepad).
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._recall = RecallTrigger(on_recall=self._hop_btn_mode)
        self._repeat = DirectionRepeat()  # auto-fire for a held direction

        self._lock = threading.Lock()
        self._app_btn_mode_trigger: str               = Trigger.CLICK
        self._device: InputDevice | None              = None
        self._refresh_requested: bool                 = False

        threading.Thread(target=self._loop, daemon=True, name="gamepad-watcher").start()

    # ── PadControl extras (Linux-specific) ─────────────────────────────────────

    def set_app_btn_mode_trigger(self, trigger: str) -> None:
        """Set the BTN_MODE recall trigger for the currently active app.

        trigger: Trigger.CLICK   — fire immediately on press (default)
                 Trigger.HOLD_1S — require a hold (see RecallTrigger.HOLD_SECONDS)
        """
        with self._lock:
            self._app_btn_mode_trigger = trigger

    def refresh(self) -> None:
        """Force the watcher thread to drop the current device and rescan.

        Some apps (notably Steam) re-enumerate gamepads when they exit:
        the kernel replaces /dev/input/eventX without our blocking read
        ever seeing an error, so the watcher silently stops receiving
        events. Calling refresh() after such an app quits forces a
        clean rebind without surfacing a fake disconnect to the UI.
        """
        with self._lock:
            if self._device is not None:
                self._refresh_requested = True

    # ── Internal ───────────────────────────────────────────────────────────

    def _emit_due_repeats(self) -> None:
        """Re-emit a held direction when its next auto-repeat is due.

        Only while our UI is in control: when the foreground app owns the pad it
        provides its own key-repeat, so synthetic repeats would double up.
        """
        if not self._stack.suppressed:
            return
        direction = self._repeat.due()
        if direction is not None:
            self._hop_nav(direction)

    def _repeat_timeout(self, default: float) -> float:
        """Shorten the blocking read so a pending auto-repeat fires on time."""
        if not self._stack.suppressed:
            return default
        return self._repeat.next_timeout(default)

    def _loop(self) -> None:
        device: InputDevice | None = None
        uinput: UInput | None      = None
        was_connected = False
        held: set[int] = set()
        # x/y track the d-pad & left stick directions; z/rz track the analog
        # triggers (volume) — sharing one dict keeps the _translate signature flat.
        stick = {"x": None, "y": None, "z": None, "rz": None}
        # Set when a refresh is in progress; if no new device is found
        # within REFRESH_GRACE_SECONDS we fall back to a real disconnect.
        refresh_started_at: float | None = None

        REFRESH_GRACE_SECONDS = 3.0
        SELECT_TIMEOUT        = 0.25

        while True:
            # ── Search for gamepad ────────────────────────────────────────
            if device is None:
                held.clear()
                stick["x"] = stick["y"] = stick["z"] = stick["rz"] = None
                self._repeat.clear()

                if uinput is not None:
                    try:
                        uinput.close()
                    except Exception:
                        pass
                    uinput = None

                found = False
                for path in list_devices():
                    try:
                        d = InputDevice(path)
                        if not self._is_gamepad(d):
                            d.close()
                            continue
                        d.grab()
                        uinput = UInput.from_device(d, name=VIRTUAL_DEVICE_NAME)
                        device = d
                        with self._lock:
                            self._device = d
                            self._refresh_requested = False
                        found = True
                        # uinput.device can be None (udev readback race / evdev
                        # version differences). Read its path defensively: this
                        # log line must NEVER throw, or it aborts the grab before
                        # the connected signal below fires and the Desktop then
                        # never auto-surfaces on startup.
                        virtual_path = getattr(uinput.device, "path", "?")
                        logger.info(
                            "Grabbed: %s  →  virtual: %s",
                            device.name, virtual_path,
                        )
                        if not was_connected:
                            was_connected = True
                            self._hop_connected()
                        refresh_started_at = None
                        break
                    except Exception as exc:
                        logger.debug("Ommitted device: %s", exc)

                if not found and refresh_started_at is not None and was_connected:
                    # Refresh in progress but no device showed up — give up
                    # the optimistic "still connected" state after a grace period.
                    if time.monotonic() - refresh_started_at > REFRESH_GRACE_SECONDS:
                        logger.info("Gamepad refresh — no device after %.1fs, signalling disconnect",
                                    REFRESH_GRACE_SECONDS)
                        was_connected = False
                        self._hop_disconnected()
                        refresh_started_at = None

            # ── Read events ───────────────────────────────────────────────
            if device:
                try:
                    pending: list[str] = []
                    while True:
                        # Honour refresh requests from other threads.
                        with self._lock:
                            if self._refresh_requested:
                                self._refresh_requested = False
                                refresh_now = True
                            else:
                                refresh_now = False
                        if refresh_now:
                            logger.info("Gamepad refresh — closing %s and rescanning", device.path)
                            self._recall.cancel()
                            self._repeat.clear()
                            refresh_started_at = time.monotonic()
                            try:
                                device.close()
                            except Exception:
                                pass
                            device = None
                            with self._lock:
                                self._device = None
                            break

                        # Block on the fd but wake periodically so the refresh
                        # flag is observable, and sooner when a held direction's
                        # next auto-repeat is due. read_loop() would block forever.
                        timeout = self._repeat_timeout(SELECT_TIMEOUT)
                        r, _, _ = select.select([device.fd], [], [], timeout)
                        if not r:
                            self._emit_due_repeats()
                            continue

                        for ev in device.read():
                            if ev.type == ecodes.EV_SYN:
                                # End of batch — emit unique navigation events
                                seen: set[str] = set()
                                for nav in pending:
                                    if nav not in seen:
                                        seen.add(nav)
                                        self._hop_nav(nav)
                                pending.clear()
                                if uinput:
                                    uinput.syn()

                            elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_MODE:
                                # BTN_MODE is never forwarded to virtual gamepad in real-time.
                                # The recall policy decides press → menu now / hold / nothing;
                                # a short press that didn't recall is forwarded on release
                                # (synthetic press+release, so Steam reacts).
                                if ev.value == 1:
                                    with self._lock:
                                        trigger = self._app_btn_mode_trigger
                                    self._recall.press(
                                        kasual_active=self._stack.suppressed,
                                        trigger=trigger,
                                    )
                                elif ev.value == 0:
                                    forward = self._recall.release(
                                        suppressed=self._stack.suppressed
                                    )
                                    if forward and uinput:
                                        uinput.write(ecodes.EV_KEY, ecodes.BTN_MODE, 1)
                                        uinput.syn()
                                        uinput.write(ecodes.EV_KEY, ecodes.BTN_MODE, 0)
                                        uinput.syn()

                            else:
                                # Forward to virtual gamepad (unless our UI is active)
                                if uinput and not self._stack.suppressed:
                                    uinput.write(ev.type, ev.code, ev.value)
                                self._translate(ev, held, stick, pending)

                        # A held direction repeats even while the analog stick
                        # streams events (so we never reach the `not r` branch).
                        self._emit_due_repeats()

                except OSError:
                    self._recall.cancel()
                    self._repeat.clear()
                    logger.info("Gamepad disconnected")
                    device = None
                    with self._lock:
                        self._device = None
                        self._refresh_requested = False
                    was_connected = False
                    refresh_started_at = None
                    self._hop_disconnected()
            else:
                time.sleep(1)

    def _translate(self, ev: InputEvent, held: set[int], stick: dict, pending: list) -> None:
        if ev.type == ecodes.EV_KEY:
            self._translate_key(ev, held, pending)
        elif ev.type == ecodes.EV_ABS:
            self._translate_axis(ev, stick, pending)

    def _translate_key(self, ev: InputEvent, held: set[int], pending: list) -> None:
        if ev.value == 1:
            held.add(ev.code)
            if ev.code == ecodes.BTN_SOUTH:
                self._hop_nav(Event.SELECT)
            elif ev.code == ecodes.BTN_EAST:
                self._hop_nav(Event.CANCEL)
            elif ev.code == ecodes.BTN_WEST:
                self._hop_nav(Event.CLOSE)
            elif ev.code == ecodes.BTN_NORTH:
                self._hop_nav(Event.ACTIONS)
            elif ev.code == ecodes.BTN_TL:
                self._hop_nav(Event.SECTION_PREV)
            elif ev.code == ecodes.BTN_TR:
                self._hop_nav(Event.SECTION_NEXT)
            elif ev.code == ecodes.BTN_START:
                # Start+Select is the home-recall chord; Start alone opens the
                # tile management popover (Select must be held first for the chord).
                if ecodes.BTN_SELECT in held:
                    self._hop_btn_mode()
                else:
                    self._hop_nav(Event.MANAGE)
        elif ev.value == 0:
            held.discard(ev.code)

    def _translate_axis(self, ev: InputEvent, stick: dict, pending: list) -> None:
        # D-pad (HAT0X/Y) has only three values: -1, 0, 1 — no hysteresis needed.
        # Analog stick (ABS_X/Y) has range -32768..32767 — handled by
        # _handle_stick_axis with threshold and hysteresis. The asymmetry is intentional.
        if ev.code == ecodes.ABS_HAT0X:
            if ev.value == -1:
                self._press_direction(stick, "x", Event.LEFT, pending)
            elif ev.value == 1:
                self._press_direction(stick, "x", Event.RIGHT, pending)
            else:
                self._release_direction(stick, "x")
        elif ev.code == ecodes.ABS_HAT0Y:
            if ev.value == -1:
                self._press_direction(stick, "y", Event.UP, pending)
            elif ev.value == 1:
                self._press_direction(stick, "y", Event.DOWN, pending)
            else:
                self._release_direction(stick, "y")
        elif ev.code == ecodes.ABS_X:
            self._handle_stick_axis(ev.value, "x", Event.LEFT, Event.RIGHT, stick, pending)
        elif ev.code == ecodes.ABS_Y:
            self._handle_stick_axis(ev.value, "y", Event.UP, Event.DOWN, stick, pending)
        elif ev.code == ecodes.ABS_Z:
            self._handle_trigger_axis(ev.value, "z", Event.VOLUME_DOWN, stick)
        elif ev.code == ecodes.ABS_RZ:
            self._handle_trigger_axis(ev.value, "rz", Event.VOLUME_UP, stick)

    def _handle_stick_axis(
        self,
        value: int,
        axis: str,
        neg_event: str,
        pos_event: str,
        stick: dict,
        pending: list,
    ) -> None:
        if value < -STICK_THRESHOLD and stick[axis] != neg_event:
            self._press_direction(stick, axis, neg_event, pending)
        elif value > STICK_THRESHOLD and stick[axis] != pos_event:
            self._press_direction(stick, axis, pos_event, pending)
        elif abs(value) < STICK_RESET:
            self._release_direction(stick, axis)

    def _handle_trigger_axis(self, value: int, key: str, event: str, stick: dict) -> None:
        """Fire one volume event when a trigger is pulled past TRIGGER_THRESHOLD.

        Unlike the stick this carries no auto-repeat — it's a discrete "nudge
        volume" gesture. The state in ``stick[key]`` latches so a held trigger
        emits once; it must relax below TRIGGER_RESET before it can fire again.
        """
        if value > TRIGGER_THRESHOLD and stick.get(key) != event:
            stick[key] = event
            self._hop_nav(event)
        elif value < TRIGGER_RESET:
            stick[key] = None

    def _press_direction(self, stick: dict, axis: str, direction: str, pending: list) -> None:
        """A direction became active: queue it, track it, and arm auto-repeat."""
        stick[axis] = direction
        pending.append(direction)
        self._repeat.press(direction)

    def _release_direction(self, stick: dict, axis: str) -> None:
        """The direction held on this axis was released: stop its auto-repeat."""
        previous = stick[axis]
        stick[axis] = None
        if previous is not None:
            self._repeat.release(previous)

    @staticmethod
    def _is_gamepad(device: InputDevice) -> bool:
        try:
            caps = device.capabilities()
            if ecodes.EV_KEY not in caps:
                return False
            keys = caps[ecodes.EV_KEY]
            gamepad_buttons = [
                ecodes.BTN_SOUTH, ecodes.BTN_EAST,
                ecodes.BTN_NORTH, ecodes.BTN_WEST,
                ecodes.BTN_START, ecodes.BTN_SELECT,
            ]
            has_hat = (
                ecodes.EV_ABS in caps
                and any(ax in caps[ecodes.EV_ABS]
                        for ax in [ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y])
            )
            return (
                any(b in keys for b in gamepad_buttons) or has_hat
            ) and ecodes.KEY_A not in keys
        except Exception:
            return False
