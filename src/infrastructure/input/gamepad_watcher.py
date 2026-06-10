import logging
import select
import threading
import time
from typing import Callable, _ProtocolMeta  # type: ignore[attr-defined]

from PyQt6.QtCore import pyqtSignal, QObject
from evdev import InputDevice, InputEvent, UInput, ecodes, list_devices

from application.input_focus import InputFocusStack
from application.recall_trigger import RecallTrigger
from domain.input import Event, Trigger
from ports import PadControl

logger = logging.getLogger(__name__)


class _Meta(type(QObject), _ProtocolMeta):
    """Combined metaclass so a QObject can declare it implements a Protocol port."""

STICK_THRESHOLD = 10000   # analog axis range: -32768..32767
STICK_RESET     = 6000    # hysteresis — below this value the axis is "centered"

VIRTUAL_DEVICE_NAME   = "kasual-vpad"

# Recall-trigger vocabulary lives in domain.input.Trigger; re-exported here for
# the historical import sites (kept str-compatible).
BTN_MODE_CLICK   = Trigger.CLICK
BTN_MODE_HOLD_1S = Trigger.HOLD_1S


class GamepadWatcher(QObject, PadControl, metaclass=_Meta):
    """
    Reads events from a physical gamepad in a background thread.

    Implements the `PadControl` port the app-lifecycle coordinator drives.

    The gamepad is always grabbed exclusively. All events except BTN_MODE
    are forwarded to a virtual gamepad (UInput, name: VIRTUAL_DEVICE_NAME),
    which external applications (e.g. Steam) use.

    Navigation events (up/down/left/right/select/cancel/close) are translated
    and dispatched through a LIFO handler stack — only the top handler reacts.
    BTN_MODE emits a separate signal (not forwarded to the stack or virtual gamepad).

    Stack interface:
        push_handler(fn)  — adds handler to the top (moves it if already present)
        pop_handler(fn)   — removes handler
        inject(event)     — injects a navigation event bypassing the gamepad (e.g. from keyboard)

    Signals:
        btn_mode_pressed()     — BTN_MODE pressed
        connected_changed(bool)
    """

    _raw              = pyqtSignal(str)    # background thread → GUI: navigation event
    btn_mode_pressed  = pyqtSignal()
    connected_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._stack = InputFocusStack()   # who receives navigation events (LIFO)
        self._recall = RecallTrigger(on_recall=self.btn_mode_pressed.emit)
        self._lock = threading.Lock()
        self._app_btn_mode_trigger: str               = Trigger.CLICK
        self._device: InputDevice | None              = None
        self._refresh_requested: bool                 = False
        self._raw.connect(self._dispatch)
        threading.Thread(target=self._loop, daemon=True, name="gamepad-watcher").start()

    # ── Public API ─────────────────────────────────────────────────────────

    def push_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.push(handler)

    def pop_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.pop(handler)

    def inject(self, event: str) -> None:
        """Inject a navigation event (e.g. from keyboard) into the active handler."""
        self._stack.dispatch(event)

    def top_handler(self) -> Callable[[str], None] | None:
        """Return the handler currently receiving events, or None if the stack is empty."""
        return self._stack.top()

    def set_app_btn_mode_trigger(self, trigger: str) -> None:
        """Set the BTN_MODE recall trigger for the currently active app.

        trigger: BTN_MODE_CLICK   — fire immediately on press (default)
                 BTN_MODE_HOLD_1S — require a hold (see RecallTrigger.HOLD_SECONDS)
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

    def _dispatch(self, event: str) -> None:
        self._stack.dispatch(event)

    def _loop(self) -> None:
        device: InputDevice | None = None
        uinput: UInput | None      = None
        was_connected = False
        held: set[int] = set()
        stick = {"x": None, "y": None}
        # Set when a refresh is in progress; if no new device is found
        # within REFRESH_GRACE_SECONDS we fall back to a real disconnect.
        refresh_started_at: float | None = None

        REFRESH_GRACE_SECONDS = 3.0
        SELECT_TIMEOUT        = 0.25

        while True:
            # ── Search for gamepad ────────────────────────────────────────
            if device is None:
                held.clear()
                stick["x"] = stick["y"] = None

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
                        logger.info(
                            "Grabbed: %s  →  virtual: %s",
                            device.name, uinput.device.path,
                        )
                        if not was_connected:
                            was_connected = True
                            self.connected_changed.emit(True)
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
                        self.connected_changed.emit(False)
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
                        # flag is observable. read_loop() would block forever.
                        r, _, _ = select.select([device.fd], [], [], SELECT_TIMEOUT)
                        if not r:
                            continue

                        for ev in device.read():
                            if ev.type == ecodes.EV_SYN:
                                # End of batch — emit unique navigation events
                                seen: set[str] = set()
                                for nav in pending:
                                    if nav not in seen:
                                        seen.add(nav)
                                        self._raw.emit(nav)
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

                except OSError:
                    self._recall.cancel()
                    logger.info("Gamepad disconnected")
                    device = None
                    with self._lock:
                        self._device = None
                        self._refresh_requested = False
                    was_connected = False
                    refresh_started_at = None
                    self.connected_changed.emit(False)
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
                self._raw.emit(Event.SELECT)
            elif ev.code == ecodes.BTN_EAST:
                self._raw.emit(Event.CANCEL)
            elif ev.code == ecodes.BTN_WEST:
                self._raw.emit(Event.CLOSE)
            elif ev.code == ecodes.BTN_START and ecodes.BTN_SELECT in held:
                self.btn_mode_pressed.emit()
        elif ev.value == 0:
            held.discard(ev.code)

    def _translate_axis(self, ev: InputEvent, stick: dict, pending: list) -> None:
        # D-pad (HAT0X/Y) has only three values: -1, 0, 1 — no hysteresis needed.
        # Analog stick (ABS_X/Y) has range -32768..32767 — handled by
        # _handle_stick_axis with threshold and hysteresis. The asymmetry is intentional.
        if ev.code == ecodes.ABS_HAT0X:
            if ev.value == -1:
                stick["x"] = Event.LEFT;  pending.append(Event.LEFT)
            elif ev.value == 1:
                stick["x"] = Event.RIGHT; pending.append(Event.RIGHT)
            else:
                stick["x"] = None
        elif ev.code == ecodes.ABS_HAT0Y:
            if ev.value == -1:
                stick["y"] = Event.UP;    pending.append(Event.UP)
            elif ev.value == 1:
                stick["y"] = Event.DOWN;  pending.append(Event.DOWN)
            else:
                stick["y"] = None
        elif ev.code == ecodes.ABS_X:
            self._handle_stick_axis(ev.value, "x", Event.LEFT, Event.RIGHT, stick, pending)
        elif ev.code == ecodes.ABS_Y:
            self._handle_stick_axis(ev.value, "y", Event.UP, Event.DOWN, stick, pending)

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
            stick[axis] = neg_event
            pending.append(neg_event)
        elif value > STICK_THRESHOLD and stick[axis] != pos_event:
            stick[axis] = pos_event
            pending.append(pos_event)
        elif abs(value) < STICK_RESET:
            stick[axis] = None

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
