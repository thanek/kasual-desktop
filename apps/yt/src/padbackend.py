"""Platform-dispatch for gamepad reading in bundled apps.

On Linux, apps read the virtual ``kasual-vpad`` evdev device via
``InputDevice.read_loop()``. On Windows, the controller is cooperative, so
apps read it directly via pygame in a background thread.

This module provides the cross-platform seam:
  - ``find_pad(names, timeout)`` — locate the gamepad (returns an opaque handle)
  - ``PadListener`` — a ``threading.Thread`` subclass whose ``run()`` reads
    events and dispatches them to browse/media handlers. Subclassed per platform.
"""

import sys
import threading
import time

_IS_WINDOWS = sys.platform == "win32"


# ── Button code constants (stable across platforms) ─────────────────────────
# On Linux these are evdev ecodes.BTN_*/ABS_*; on Windows they are pygame
# button indices / axis indices. The app-facing PadListener maps raw events to
# these string codes so the browse/media handlers stay platform-agnostic.
BTN_SOUTH = "BTN_SOUTH"   # A
BTN_EAST = "BTN_EAST"     # B
BTN_NORTH = "BTN_NORTH"   # Y
BTN_WEST = "BTN_WEST"     # X
BTN_TL = "BTN_TL"         # LB
BTN_TR = "BTN_TR"         # RB
ABS_HAT0X = "ABS_HAT0X"   # D-pad X
ABS_HAT0Y = "ABS_HAT0Y"   # D-pad Y
ABS_Z = "ABS_Z"           # LT
ABS_RZ = "ABS_RZ"         # RT
ABS_RX = "ABS_RX"         # Right stick X
ABS_RY = "ABS_RY"         # Right stick Y
ABS_Y = "ABS_Y"           # Left stick Y


class PadEvent:
    """Platform-agnostic gamepad event: a button code + value, or an axis code + value."""

    __slots__ = ("kind", "code", "value")

    def __init__(self, kind: str, code: str, value: int) -> None:
        # kind: "key" (button, value 1=press 0=release) or "abs" (axis, value is raw)
        self.kind = kind
        self.code = code
        self.value = value


if _IS_WINDOWS:
    import pygame

    # Initialise pygame in the main thread (import time) — pygame's event queue
    # is pumped by SDL's video subsystem, so display.init() is required for
    # JOYBUTTONDOWN / JOYAXISMOTION / JOYHATMOTION to be delivered. Doing this
    # at module level (rather than in find_pad) ensures it runs on the main
    # thread, mirroring infrastructure.windows.gamepad_watcher.
    pygame.init()
    pygame.joystick.init()
    pygame.display.init()

    # pygame button indices (XInput/SDL convention, matches the main Kasual
    # gamepad_watcher). Verified on an 8BitDo Ultimate in X-input mode.
    _PG_BTN_SOUTH = 0   # A
    _PG_BTN_EAST = 1    # B
    _PG_BTN_WEST = 2    # X
    _PG_BTN_NORTH = 3   # Y
    _PG_BTN_TL = 4      # LB
    _PG_BTN_TR = 5      # RB

    _PG_AXIS_LEFT_X = 0
    _PG_AXIS_LEFT_Y = 1
    _PG_AXIS_RIGHT_X = 2
    _PG_AXIS_RIGHT_Y = 3
    _PG_AXIS_LT = 4     # left trigger  (-1 rest .. 1 pressed)
    _PG_AXIS_RT = 5     # right trigger (-1 rest .. 1 pressed)

    _TRIGGER_THRESHOLD = 0.2  # normalized: trigger pressed when value > this

    class _PygamePad:
        """Opaque handle returned by find_pad on Windows — wraps a pygame Joystick."""

        def __init__(self, joystick: "pygame.joystick.Joystick") -> None:
            self._joy = joystick

    def find_pad(names: list[str], timeout: float = 10.0) -> _PygamePad:
        """Find the first connected gamepad via pygame.

        On Windows the controller is cooperative (Kasual doesn't grab it), so
        we just take the first joystick. The *names* argument is ignored —
        we don't filter by device name because XInput doesn't expose evdev
        names. *timeout* is respected for the wait-for-connect case.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pygame.joystick.get_count() > 0:
                joy = pygame.joystick.Joystick(0)
                joy.init()
                return _PygamePad(joy)
            time.sleep(0.2)
        raise RuntimeError("No gamepad connected (pygame found 0 joysticks)")

    class PadListener(threading.Thread):
        """Reads gamepad state via pygame polling and dispatches events.

        Uses direct joystick polling (``get_button``/``get_hat``/``get_axis``)
        instead of SDL events — more reliable in a process that has a Qt window
        (SDL and Qt compete for the Windows message pump, and event delivery
        from a background thread can be unreliable).

        Subclasses override ``on_key(code)`` and ``on_axis(code, value)``.
        """

        def __init__(self, pad: _PygamePad, window=None) -> None:
            super().__init__(daemon=True)
            self._pad = pad
            self._joy = pad._joy
            self._window = window
            self._mode = "browse"
            self._stick_x = 0.0
            self._stick_y = 0.0
            self._left_y = 0.0
            self._running = True
            # Previous button states (for edge detection).
            self._prev_buttons: dict[int, bool] = {}
            # Previous hat state.
            self._prev_hat = (0, 0)
            # Previous axis states (for edge / threshold-crossing detection).
            self._prev_axes: dict[int, float] = {}

        def set_mode(self, mode: str) -> None:
            self._mode = mode
            self._stick_x = 0.0
            self._stick_y = 0.0
            self._left_y = 0.0

        @property
        def stick(self) -> tuple[float, float]:
            return (self._stick_x, self._stick_y)

        @property
        def left_y(self) -> float:
            return self._left_y

        def stop(self) -> None:
            self._running = False

        def run(self) -> None:
            clock = pygame.time.Clock()
            num_buttons = self._joy.get_numbuttons()
            num_axes = self._joy.get_numaxes()
            while self._running:
                clock.tick(60)
                # Pump the SDL event queue so joystick state is refreshed —
                # without this, get_button/get_hat/get_axis return stale values.
                # (pygame gotcha: SDL_JoystickUpdate is called by event.pump.)
                pygame.event.pump()
                if self._window is not None and not self._window.isActiveWindow():
                    continue

                # Poll buttons — emit on press edge (False → True).
                for i in range(num_buttons):
                    pressed = bool(self._joy.get_button(i))
                    if pressed and not self._prev_buttons.get(i, False):
                        code = self._button_code(i)
                        if code is not None:
                            self.on_key(code)
                    self._prev_buttons[i] = pressed

                # Poll D-pad (hat) — emit on change.
                # pygame hat: y=1 is UP, y=-1 is DOWN (mathematical convention).
                # evdev ABS_HAT0Y: y=-1 is UP, y=1 is DOWN (screen convention).
                # Invert Y so the app's evdev-style handlers work unchanged.
                hat = self._joy.get_hat(0)
                hat = (hat[0], -hat[1])
                if hat != self._prev_hat:
                    prev_x, prev_y = self._prev_hat
                    x, y = hat
                    if x != prev_x:
                        self.on_axis(ABS_HAT0X, x, prev_x)
                    if y != prev_y:
                        self.on_axis(ABS_HAT0Y, y, prev_y)
                    self._prev_hat = hat

                # Poll analog axes — emit on threshold crossing.
                for i in range(num_axes):
                    raw = self._joy.get_axis(i)
                    code = self._axis_code(i)
                    if code is None:
                        continue
                    prev = self._prev_axes.get(i)
                    # Update stick/left_y properties from analog axes.
                    if i == _PG_AXIS_RIGHT_X:
                        self._stick_x = self._normalize(raw)
                    elif i == _PG_AXIS_RIGHT_Y:
                        self._stick_y = self._normalize(raw)
                    elif i == _PG_AXIS_LEFT_Y:
                        self._left_y = self._normalize(raw)
                    # Emit when the value crosses a meaningful threshold.
                    if prev is None or self._crossed(raw, prev):
                        self.on_axis(code, raw, prev)
                    self._prev_axes[i] = raw

        @staticmethod
        def _crossed(curr: float, prev: float) -> bool:
            """True when the axis crossed the dead-zone boundary in either direction."""
            threshold = 0.3
            return abs(curr) > threshold != abs(prev) > threshold

        @staticmethod
        def _button_code(pg_button: int) -> str | None:
            return {
                _PG_BTN_SOUTH: BTN_SOUTH,
                _PG_BTN_EAST: BTN_EAST,
                _PG_BTN_WEST: BTN_WEST,
                _PG_BTN_NORTH: BTN_NORTH,
                _PG_BTN_TL: BTN_TL,
                _PG_BTN_TR: BTN_TR,
            }.get(pg_button)

        @staticmethod
        def _axis_code(pg_axis: int) -> str | None:
            return {
                _PG_AXIS_LT: ABS_Z,
                _PG_AXIS_RT: ABS_RZ,
                _PG_AXIS_RIGHT_X: ABS_RX,
                _PG_AXIS_RIGHT_Y: ABS_RY,
                _PG_AXIS_LEFT_Y: ABS_Y,
            }.get(pg_axis)

        @staticmethod
        def _normalize(value: float) -> float:
            """Normalize a pygame axis value (-1..1) with a dead zone."""
            if abs(value) < 0.15:
                return 0.0
            return value

        # ── App-facing hooks (override in subclass) ───────────────────────────
        def on_key(self, code: str) -> None:
            """Called on a button press (edge False→True). Override in subclass."""

        def on_axis(self, code: str, value: float, prev: float | None) -> None:
            """Called on an axis change. Override in subclass. *value* is the raw
            pygame axis value (-1..1 for sticks/triggers, -1/0/1 for D-pad)."""

else:
    from evdev import InputDevice, ecodes, list_devices

    class _EvdevPad:
        """Opaque handle returned by find_pad on Linux — wraps an evdev InputDevice."""

        def __init__(self, device: InputDevice) -> None:
            self._dev = device
            # absinfo for normalization (populated lazily by PadListener).
            self.rx_info = None
            self.ry_info = None
            self.ly_info = None

    def find_pad(names: list[str], timeout: float = 10.0) -> _EvdevPad:
        """Wait for an evdev device with one of *names*, max *timeout* seconds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for path in list_devices():
                try:
                    d = InputDevice(path)
                    if d.name in names:
                        return _EvdevPad(d)
                    d.close()
                except Exception:
                    pass
            time.sleep(0.2)
        raise RuntimeError(f"Pad not found among: {names}")

    class PadListener(threading.Thread):
        """Reads gamepad events via evdev and dispatches platform-agnostic PadEvents.

        Subclasses override ``on_key(code)`` and ``on_axis(code, value, prev)`` to
        implement browse/media mode. The ``stick``/``left_y`` properties are
        updated from right-stick / left-stick-Y axes.
        """

        def __init__(self, pad: _EvdevPad, window=None) -> None:
            super().__init__(daemon=True)
            self._pad = pad
            self._window = window
            self._mode = "browse"
            self._stick_x = 0.0
            self._stick_y = 0.0
            self._left_y = 0.0
            self._running = True
            try:
                self._rx_info = pad._dev.absinfo(ecodes.ABS_RX)
            except Exception:
                self._rx_info = None
            try:
                self._ry_info = pad._dev.absinfo(ecodes.ABS_RY)
            except Exception:
                self._ry_info = None
            try:
                self._ly_info = pad._dev.absinfo(ecodes.ABS_Y)
            except Exception:
                self._ly_info = None

        def set_mode(self, mode: str) -> None:
            self._mode = mode
            self._stick_x = 0.0
            self._stick_y = 0.0
            self._left_y = 0.0

        @property
        def stick(self) -> tuple[float, float]:
            return (self._stick_x, self._stick_y)

        @property
        def left_y(self) -> float:
            return self._left_y

        def stop(self) -> None:
            self._running = False

        def run(self) -> None:
            dev = self._pad._dev
            for ev in dev.read_loop():
                if not self._running:
                    break
                if self._window is not None and not self._window.isActiveWindow():
                    continue
                code = self._translate_code(ev.type, ev.code)
                if code is None:
                    continue
                if ev.type == ecodes.EV_KEY and ev.value == 1:
                    self.on_key(code)
                elif ev.type == ecodes.EV_ABS:
                    prev = None
                    if code == ecodes.ABS_RX:
                        prev = self._stick_x
                        self._stick_x = self._normalize(ev.value, self._rx_info)
                    elif code == ecodes.ABS_RY:
                        prev = self._stick_y
                        self._stick_y = self._normalize(ev.value, self._ry_info)
                    elif code == ecodes.ABS_Y:
                        prev = self._left_y
                        self._left_y = self._normalize(ev.value, self._ly_info)
                    self.on_axis(code, ev.value, prev)

        @staticmethod
        def _translate_code(ev_type: int, ev_code: int) -> str | None:
            if ev_type == ecodes.EV_KEY:
                return {
                    ecodes.BTN_SOUTH: BTN_SOUTH,
                    ecodes.BTN_EAST: BTN_EAST,
                    ecodes.BTN_WEST: BTN_WEST,
                    ecodes.BTN_NORTH: BTN_NORTH,
                    ecodes.BTN_TL: BTN_TL,
                    ecodes.BTN_TR: BTN_TR,
                }.get(ev_code)
            if ev_type == ecodes.EV_ABS:
                return {
                    ecodes.ABS_HAT0X: ABS_HAT0X,
                    ecodes.ABS_HAT0Y: ABS_HAT0Y,
                    ecodes.ABS_Z: ABS_Z,
                    ecodes.ABS_RZ: ABS_RZ,
                    ecodes.ABS_RX: ABS_RX,
                    ecodes.ABS_RY: ABS_RY,
                    ecodes.ABS_Y: ABS_Y,
                }.get(ev_code)
            return None

        @staticmethod
        def _normalize(value: int, info) -> float:
            if info is None:
                return 0.0
            center = (info.min + info.max) / 2
            half = (info.max - info.min) / 2
            if half == 0:
                return 0.0
            raw = (value - center) / half
            if abs(raw) < 0.15:
                return 0.0
            return raw

        # ── App-facing hooks (override in subclass) ───────────────────────────
        def on_key(self, code: str) -> None:
            """Called on a button press (value=1). Override in subclass."""

        def on_axis(self, code: str, value: int, prev: int | None) -> None:
            """Called on an axis change. Override in subclass. *value* is the raw
            evdev axis value (e.g. -32768..32767 for sticks, -1..1 for D-pad,
            0..255 for triggers)."""
