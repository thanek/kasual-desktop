"""
Windows gamepad implementation using pygame's SDL **GameController** API.

Two modes, decided at startup by driver_probe:

  * **Exclusive** (ViGEmBus + HidHide both installed): the physical gamepad is
    hidden from other processes by HidHide; Kasual reads it via pygame (its
    image path is whitelisted) and forwards events to a virtual Xbox360 pad
    (``kasual-vpad``) through ViGEmBus. Steam/games/bundled-apps see only the
    virtual pad. When Kasual's own UI is active (``stack.suppressed``),
    forwarding is gated off — the virtual pad goes quiet, eliminating the
    "cooperative bleed" where two apps navigate the same pad at once.

  * **Cooperative** (either driver missing): the legacy behaviour — ALL apps
    see gamepad events simultaneously, no virtual pad, no gating. This is the
    fallback per D4 (all-or-nothing): ViGEm without HidHide would make Steam
    see *both* pads, which is worse than cooperative.

BTN_MODE handling mirrors the Linux (KDE) model in exclusive mode: a short
press that didn't recall the Kasual menu is forwarded to the virtual pad as a
synthetic guide press+release (so Steam still sees its guide button). In
cooperative mode the synthetic forward is moot (the app already saw the press).

Why the GameController API (and not the raw joystick API)? Raw joystick button
*indices* are device- and mode-specific. An 8BitDo Ultimate in X-input mode, for
example, enumerates as an "Xbox 360 Controller for Windows" whose D-pad arrives
as buttons (D-pad-up = button 10) and whose Guide button isn't exposed at all —
so a hardcoded index table silently maps D-pad-up onto BTN_MODE and never sees
Guide. SDL's GameController layer applies its controller database to give stable
*semantic* buttons (A/B/X/Y, D-pad, Guide) and normalised axes regardless of the
controller, which is what the rest of this class relies on.
"""

import logging
import os
import threading
import time
from typing import Callable

# Force SDL to read XInput controllers through the XInput backend rather than
# RawInput. SDL's RawInput path enumerates Xbox / 8BitDo-X-input pads several
# times over and only recovers the Guide button by correlating with XInput — a
# correlation that silently fails on some setups, leaving BTN_MODE (Guide) dead
# and the pad enumerated 4×. The XInput backend reads Guide directly (via
# XInputGetStateEx). This must be set before SDL initialises its joystick
# subsystem; setdefault lets an explicit environment override stand.
os.environ.setdefault("SDL_JOYSTICK_RAWINPUT", "0")

import pygame
from pygame._sdl2 import controller as game_controller
from PyQt6.QtCore import QObject, pyqtSignal

from domain.input.gamepad_events import (
    BtnModePressed,
    GamepadConnected,
    GamepadDisconnected,
)
from domain.input.direction_repeat import DirectionRepeat
from domain.input.focus_stack import InputFocusStack
from domain.input.gamepad_signals import GamepadSignals
from domain.input.pad_control import PadControl
from domain.input.recall import RecallTrigger
from domain.input.vocabulary import Event, Trigger
from domain.shared.event_emitter import EventEmitter, Unsubscribe
from infrastructure.windows.input.driver_probe import DriverCapabilities, probe_drivers

logger = logging.getLogger(__name__)

# SDL GameController axes report int16: sticks -32768..32767, triggers 0..32767.
STICK_THRESHOLD = 16000
STICK_RESET = 8000

# How long the synthetic Guide (BTN_MODE short-press) pulse is held on the
# virtual pad. Unlike evdev — where the press+release are two timestamped
# events Steam always sees — an XInput consumer polls the pad state at ~60-250
# Hz, so a zero-duration pulse can fall between polls and be missed. Holding it
# for a few frames guarantees the guide tap is observed.
GUIDE_PULSE_SECONDS = 0.05

# Semantic buttons from the SDL GameController API. SDL's controller database
# maps every supported pad onto these, so they are correct across Xbox, 8BitDo
# (X-input → reports as Xbox360, D-pad as buttons, Guide via XInput), DualSense,
# etc. — unlike raw joystick indices, which differ per device/mode.
BTN_SOUTH  = pygame.CONTROLLER_BUTTON_A             # A
BTN_EAST   = pygame.CONTROLLER_BUTTON_B             # B
BTN_WEST   = pygame.CONTROLLER_BUTTON_X             # X
BTN_NORTH  = pygame.CONTROLLER_BUTTON_Y             # Y
BTN_SELECT = pygame.CONTROLLER_BUTTON_BACK          # Back / View
BTN_START  = pygame.CONTROLLER_BUTTON_START         # Start / Menu
BTN_MODE   = pygame.CONTROLLER_BUTTON_GUIDE         # Guide / Home
BTN_TL     = pygame.CONTROLLER_BUTTON_LEFTSHOULDER  # LB
BTN_TR     = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER # RB
DPAD_UP    = pygame.CONTROLLER_BUTTON_DPAD_UP
DPAD_DOWN  = pygame.CONTROLLER_BUTTON_DPAD_DOWN
DPAD_LEFT  = pygame.CONTROLLER_BUTTON_DPAD_LEFT
DPAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT

# D-pad button → navigation direction (also the auto-repeat key). With the
# GameController API the D-pad is always discrete buttons, never a hat.
_DPAD_TO_EVENT = {
    DPAD_UP:    Event.UP,
    DPAD_DOWN:  Event.DOWN,
    DPAD_LEFT:  Event.LEFT,
    DPAD_RIGHT: Event.RIGHT,
}

AXIS_LEFTX = pygame.CONTROLLER_AXIS_LEFTX
AXIS_LEFTY = pygame.CONTROLLER_AXIS_LEFTY


class _Bridge(QObject):
    """Qt-signal bridge: emitted from the pygame thread, delivered on the main thread."""
    nav    = pyqtSignal(str)
    btn    = pyqtSignal()          # BTN_MODE
    conn   = pyqtSignal()
    disc   = pyqtSignal()


class WindowsGamepadWatcher(PadControl, GamepadSignals):
    """
    Reads events from a gamepad using pygame's GameController API in a
    background thread.

    Implements two domain ports: `PadControl` and `GamepadSignals`.

    On Windows, gamepads are cooperative - all applications see all events.
    We don't use grab() because Windows doesn't support it without a kernel driver.

    Threading: the read loop runs on a background thread, but all observers
    run on the GUI thread via pyqtSignals for Qt integration.

    Stack interface:
        push_handler(fn)  - adds handler to the top
        pop_handler(fn)   - removes handler
        inject(event)     - injects a navigation event from keyboard
    """

    def __init__(self, parent=None):
        self._parent = parent
        self._stack = InputFocusStack()
        self._connected = False
        self._running = True
        # A pad can enumerate as several SDL controllers at once: a DInput/HID
        # view (no Guide button) plus one or more XInput views (Guide button
        # present, but only readable via the XInput backend — hence the
        # SDL_JOYSTICK_RAWINPUT=0 hint above). We open EVERY view and read from
        # all of them, deduping duplicate button-downs of the same physical
        # press (see _handle_button_down). That way Guide events (which only the
        # XInput view emits) get through without us having to guess which view /
        # XInput slot carries the real input. Keyed by SDL instance id.
        self._controllers: dict[int, object] = {}

        # Driver probe: exclusive mode requires BOTH ViGEmBus and HidHide.
        # If either is missing, fall back to cooperative (D4 all-or-nothing).
        self._caps = probe_drivers()
        self._exclusive = self._caps.exclusive
        if self._exclusive:
            logger.info("Gamepad mode: exclusive (ViGEmBus + HidHide)")
        else:
            logger.warning(
                "Gamepad mode: cooperative (ViGEmBus=%s, HidHide=%s) — "
                "pad bleed to foreground apps will occur. "
                "Install both drivers for exclusive control.",
                self._caps.vigembus, self._caps.hidhide,
            )

        # Exclusive-mode state (None in cooperative mode). Setup/teardown can be
        # driven from the read loop (connect/disconnect) AND the GUI thread
        # (refresh/shutdown), so they are serialised by a reentrant lock — the
        # except path in _setup_exclusive re-enters via _teardown_exclusive.
        self._writer = None        # VigemWriter, set on gamepad connect
        self._hidhide = None       # HidHideClient, set on gamepad connect
        self._pad_instance_ids: list[str] = []  # for unhide on disconnect/shutdown
        self._exclusive_lock = threading.RLock()
        # Last suppressed state seen by the loop — so the moment our UI takes
        # over we can neutralise the virtual pad once (release any held input),
        # rather than leaving a button/stick stuck down under the foreground app.
        self._last_suppressed = False

        self._btn_mode_emitter = EventEmitter[BtnModePressed]()
        self._connected_emitter = EventEmitter[GamepadConnected]()
        self._disconnected_emitter = EventEmitter[GamepadDisconnected]()

        # Bridge: pygame events arrive on background thread; signals are
        # delivered to the main thread via Qt's queued-connection mechanism.
        self._bridge = _Bridge()
        self._bridge.nav.connect(self._on_nav_main)
        self._bridge.btn.connect(self._on_btn_mode_main)
        self._bridge.conn.connect(self._on_connected_main)
        self._bridge.disc.connect(self._on_disconnected_main)

        # BTN_MODE recall policy: per the foreground app's trigger, a quick guide
        # press is left to the app (e.g. Steam's own menu — the controller is
        # cooperative on Windows, so Steam sees it natively) and only a ~1 s HOLD
        # opens the Kasual menu. When Kasual itself is in control (a handler on the
        # stack) recall is always immediate. The hold timer fires on_recall on a
        # background thread; bridge.btn marshals it to the GUI thread.
        self._app_trigger = Trigger.CLICK
        self._recall = RecallTrigger(on_recall=self._bridge.btn.emit)

        pygame.init()
        pygame.joystick.init()
        game_controller.init()
        pygame.display.init()

        self._held = set()
        self._stick = {"x": None, "y": None}
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

        while self._running:
            clock.tick(60)

            try:
                events = pygame.event.get()
            except Exception as e:
                logger.warning("Error getting pygame events: %s", e)
                continue

            for event in events:
                if event.type == pygame.CONTROLLERDEVICEADDED:
                    try:
                        ctrl = game_controller.Controller(event.device_index)
                    except Exception as exc:
                        logger.warning("Could not open controller %s: %s",
                                       event.device_index, exc)
                        continue
                    was_empty = not self._controllers
                    self._controllers[ctrl.id] = ctrl
                    logger.info("Controller added: %s (%d view(s) open)",
                                ctrl.name, len(self._controllers))
                    if was_empty:
                        self._connected = True
                        self._setup_exclusive()
                        self._emit_connected()

                elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                    ctrl = self._controllers.pop(event.instance_id, None)
                    if ctrl is not None:
                        try:
                            ctrl.quit()
                        except Exception:
                            pass
                    if self._connected and not self._controllers:
                        logger.info("Controller disconnected")
                        self._connected = False
                        self._teardown_exclusive()
                        self._repeat.clear()
                        self._recall.cancel()
                        self._stick = {"x": None, "y": None}
                        self._emit_disconnected()

                elif event.type == pygame.CONTROLLERBUTTONDOWN:
                    self._handle_button_down(event.button)

                elif event.type == pygame.CONTROLLERBUTTONUP:
                    self._handle_button_up(event.button)

                elif event.type == pygame.CONTROLLERAXISMOTION:
                    self._handle_axis(event.axis, event.value)

            # Re-emit the held direction when its next auto-repeat is due.
            repeated = self._repeat.due()
            if repeated is not None:
                self._dispatch(repeated)

            # When our UI takes control (suppressed flips True), forwarding to
            # the virtual pad stops mid-input — any button/stick held at that
            # instant would otherwise stay latched down under the foreground
            # app. Release everything once on the transition.
            suppressed = self._stack.suppressed
            if suppressed and not self._last_suppressed:
                writer = self._writer
                if writer is not None:
                    writer.reset()
            self._last_suppressed = suppressed

    def _handle_button_down(self, button: int):
        """Handle button press.

        When a pad is open as several views (DInput + XInput), one physical
        press arrives once per view. The held-set dedups it: a button already
        held is a duplicate from another view and is ignored, so navigation
        fires once. (Button-up is naturally idempotent — releasing an already-
        released button is a no-op — so it needs no guard.)
        """
        if button in self._held:
            return
        self._held.add(button)
        logger.debug("Button down: %d", button)

        if button == BTN_MODE:
            # CLICK / Kasual active → recall now; HOLD_1S app → arm the hold.
            # Never forwarded as a normal button — only as a synthetic guide
            # pulse on release (see _handle_button_up).
            self._recall.press(kasual_active=self._stack.suppressed, trigger=self._app_trigger)
            return

        self._forward_button(button, 1)
        if button == BTN_SOUTH:
            self._dispatch(Event.SELECT)
        elif button == BTN_EAST:
            self._dispatch(Event.CANCEL)
        elif button == BTN_NORTH:
            self._dispatch(Event.CLOSE)
        elif button == BTN_START:
            if BTN_SELECT in self._held:
                self._bridge.btn.emit()
            else:
                self._dispatch(Event.MANAGE)
        else:
            direction = _DPAD_TO_EVENT.get(button)
            if direction is not None:
                self._dispatch(direction)
                self._repeat.press(direction)

    def _handle_button_up(self, button: int):
        """Handle button release."""
        self._held.discard(button)
        if button == BTN_MODE:
            # Cancels a pending hold. The return value reports whether a
            # short-press synthetic forward to the app is due. In cooperative
            # mode this is moot (the app already saw the press). In exclusive
            # mode the app never saw the physical press (HidHide hid it), so
            # we must forward a synthetic guide press+release to ViGEm —
            # mirroring the Linux evdev BTN_MODE synthetic forward.
            forward = self._recall.release(suppressed=self._stack.suppressed)
            writer = self._writer
            if forward and writer is not None:
                writer.set_guide(True)
                time.sleep(GUIDE_PULSE_SECONDS)
                writer.set_guide(False)
            return

        self._forward_button(button, 0)
        direction = _DPAD_TO_EVENT.get(button)
        if direction is not None:
            self._repeat.release(direction)

    def _handle_axis(self, axis: int, value: int):
        """Handle analog stick movement (left stick navigates; others forward only)."""
        self._forward_axis(axis, value)
        if axis == AXIS_LEFTX:
            self._handle_stick_axis("x", value, Event.LEFT, Event.RIGHT)
        elif axis == AXIS_LEFTY:
            self._handle_stick_axis("y", value, Event.UP, Event.DOWN)

    def _handle_stick_axis(self, axis: str, value: int, neg_event: str, pos_event: str):
        """Handle stick axis with threshold and hysteresis."""
        if value < -STICK_THRESHOLD and self._stick[axis] != neg_event:
            self._stick[axis] = neg_event
            self._dispatch(neg_event)
            self._repeat.press(neg_event)
        elif value > STICK_THRESHOLD and self._stick[axis] != pos_event:
            self._stick[axis] = pos_event
            self._dispatch(pos_event)
            self._repeat.press(pos_event)
        elif abs(value) < STICK_RESET:
            if self._stick[axis] is not None:
                self._repeat.release(self._stick[axis])
            self._stick[axis] = None

    # ── Exclusive-mode forwarding to ViGEm ─────────────────────────────────

    def _forward_button(self, button: int, value: int) -> None:
        """Forward a button event to the virtual pad (exclusive mode only).

        Gated by ``not self._stack.suppressed``: when Kasual's UI is active,
        the virtual pad goes quiet so foreground apps don't react. BTN_MODE is
        never forwarded here — it goes through the synthetic guide pulse in
        ``_handle_button_up``.

        ``self._writer`` is read into a local once: teardown (on another thread)
        may null it between the guard and the call, so the local keeps the write
        consistent without locking the per-event hot path.
        """
        writer = self._writer
        if writer is not None and not self._stack.suppressed:
            writer.write_button(button, value)

    def _forward_axis(self, axis: int, value: int) -> None:
        """Forward an analog axis to the virtual pad (exclusive mode only)."""
        writer = self._writer
        if writer is not None and not self._stack.suppressed:
            writer.write_axis(axis, value)

    def _setup_exclusive(self) -> None:
        """Set up HidHide + ViGEm when a gamepad connects (exclusive mode).

        If no physical gamepad HID node can be found to hide, we deliberately do
        NOT create the virtual pad. HidHide can only cloak devices on the HID
        stack; an XInput-only controller (Xbox / 8BitDo X-input) exposes no such
        node, so its events would still bleed to the foreground app via XInput.
        Adding a virtual pad on top of that would make Steam see *two* pads —
        worse than cooperative. So we fall back to cooperative for the session
        (D4 all-or-nothing): single physical pad, no isolation, no duplicate.
        """
        if not self._exclusive:
            return
        with self._exclusive_lock:
            try:
                from infrastructure.windows.input.hidhide import HidHideClient
                from infrastructure.windows.input.vigembus_writer import VigemWriter

                instance_ids = HidHideClient.resolve_gamepad_instance_ids()
                # XInput-backed pads carry "IG_" (Interface Gamepad) in their HID
                # instance path. Steam/games read those through the XInput API
                # (xusb), which HidHide CANNOT cloak — hiding their HID node
                # leaves them visible via XInput while we add the virtual pad on
                # top, so the foreground app sees TWO pads (worse than
                # cooperative). Only pure DInput/HID gamepads (no IG_) can truly
                # be isolated; for an XInput pad we fall back to cooperative.
                hideable = [i for i in instance_ids if "IG_" not in i.upper()]
                if not hideable:
                    logger.warning(
                        "Exclusive mode: the gamepad is XInput-backed (HID path "
                        "has IG_) or exposes no hideable HID node — HidHide cannot "
                        "hide it from the XInput API. Falling back to cooperative "
                        "to avoid a duplicate virtual pad. Switch the controller "
                        "to DirectInput mode for full isolation."
                    )
                    return

                self._hidhide = HidHideClient()
                self._hidhide.register_self()
                # Blacklisting a device only cloaks it while the filter is
                # active; without this the physical pad stays visible.
                self._hidhide.set_active(True)
                self._pad_instance_ids = hideable
                for instance_id in hideable:
                    self._hidhide.hide_device(instance_id)

                self._writer = VigemWriter(name="kasual-vpad")
                self._writer.connect()
            except Exception as exc:
                logger.warning("Exclusive mode setup failed, falling back: %s", exc)
                self._teardown_exclusive()

    def _teardown_exclusive(self) -> None:
        """Tear down HidHide + ViGEm when a gamepad disconnects."""
        with self._exclusive_lock:
            if self._writer is not None:
                try:
                    self._writer.disconnect()
                except Exception:
                    pass
                self._writer = None
            if self._hidhide is not None:
                try:
                    self._hidhide.unhide_all()
                    self._hidhide.close()
                except Exception:
                    pass
                self._hidhide = None
            self._pad_instance_ids = []

    def _dispatch(self, event: str):
        """Queue event for delivery on the Qt main thread."""
        self._bridge.nav.emit(event)

    def _emit_connected(self):
        self._bridge.conn.emit()

    def _emit_disconnected(self):
        self._bridge.disc.emit()

    # ── Main-thread slots (called via Qt queued connection) ──────────────────

    def _on_nav_main(self, event: str) -> None:
        logger.debug("Dispatching event: %s", event)
        self._stack.dispatch(event)

    def _on_btn_mode_main(self) -> None:
        self._btn_mode_emitter.emit(BtnModePressed())

    def _on_connected_main(self) -> None:
        self._connected_emitter.emit(GamepadConnected())

    def _on_disconnected_main(self) -> None:
        self._disconnected_emitter.emit(GamepadDisconnected())

    def on_btn_mode(self, handler: Callable[[], None]) -> Unsubscribe:
        return self._btn_mode_emitter.subscribe(lambda _evt: handler())

    def on_connected(self, handler: Callable[[GamepadConnected], None]) -> Unsubscribe:
        return self._connected_emitter.subscribe(handler)

    def on_disconnected(self, handler: Callable[[GamepadDisconnected], None]) -> Unsubscribe:
        return self._disconnected_emitter.subscribe(handler)

    def push_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.push(handler)

    def pop_handler(self, handler: Callable[[str], None]) -> None:
        self._stack.pop(handler)

    def inject(self, event: str) -> None:
        """Inject a navigation event (e.g. from keyboard)."""
        self._dispatch(event)

    def top_handler(self) -> Callable[[str], None] | None:
        return self._stack.top()

    def trigger_btn_mode(self) -> None:
        """Request BTN_MODE from outside (e.g. keyboard shortcut)."""
        self._btn_mode_emitter.emit(BtnModePressed())

    def trigger_home(self) -> None:
        self.trigger_btn_mode()

    def set_app_btn_mode_trigger(self, trigger: str) -> None:
        """Set how BTN_MODE recalls the Kasual menu for the current foreground:
        ``Trigger.CLICK`` (immediate) or ``Trigger.HOLD_1S`` (require a ~1 s hold,
        leaving a quick press to the app). Driven by AppLifecycle as apps come and
        go; the trigger stays put for a whole app session (so a launcher's child
        games inherit it) until the Desktop is reactivated (reset to CLICK)."""
        self._app_trigger = trigger

    def refresh(self) -> None:
        """Reinitialize the controller subsystem (e.g. after a foreground app exits).

        Tears the virtual pad / HidHide cloak down and rebuilds them: an app
        like Steam may have plugged its own ViGEm targets or toggled HidHide
        while running, so after it quits we re-establish our own exclusive setup
        rather than leaving the physical pad unhidden and the virtual pad gone.
        """
        self._teardown_exclusive()
        self._repeat.clear()
        self._recall.cancel()
        for ctrl in self._controllers.values():
            try:
                ctrl.quit()
            except Exception:
                pass
        self._controllers = {}
        self._active_id = None
        pygame.joystick.quit()
        pygame.joystick.init()
        game_controller.quit()
        game_controller.init()
        if self._connected:
            self._setup_exclusive()

    def shutdown(self):
        """Stop the watcher thread and clean up exclusive-mode resources."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._teardown_exclusive()
        for ctrl in self._controllers.values():
            try:
                ctrl.quit()
            except Exception:
                pass
        self._controllers = {}
        self._active_id = None
        pygame.quit()
