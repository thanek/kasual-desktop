"""Gamepad input for image_viewer: buttons, analog triggers, and right-stick pan."""

import threading
import time

from evdev import InputDevice, UInput, ecodes, list_devices
from evdev import ecodes as e


_ui = UInput()
_TRIGGER_THRESHOLD = 200
_DEAD_ZONE = 0.15


def _press(key: int) -> None:
    _ui.write(e.EV_KEY, key, 1)
    _ui.write(e.EV_KEY, key, 0)
    _ui.syn()


def find_pad(names: list[str], timeout: float = 10.0) -> InputDevice:
    """Waits for a gamepad with one of the given names to appear, up to timeout seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in list_devices():
            try:
                d = InputDevice(path)
                if d.name in names:
                    return d
                d.close()
            except Exception:
                pass
        time.sleep(0.2)
    raise RuntimeError(f"Pad not found among: {names}")


def _normalize(value: int, info) -> float:
    """Map raw axis value to -1..1 with dead zone applied."""
    if info is None:
        return 0.0
    center = (info.min + info.max) / 2
    half = (info.max - info.min) / 2
    if half == 0:
        return 0.0
    raw = (value - center) / half
    if abs(raw) < _DEAD_ZONE:
        return 0.0
    sign = 1.0 if raw > 0 else -1.0
    return sign * (abs(raw) - _DEAD_ZONE) / (1.0 - _DEAD_ZONE)


class PadListener(threading.Thread):
    """
    Translates gamepad events for image_viewer.

    Mapping:
        B (BTN_EAST)           → Escape   (reset zoom / exit)
        RB (BTN_TR)            → Page Down (next image)
        LB (BTN_TL)            → Page Up   (prev image)
        RIGHT_TRIGGER (ABS_RZ) → Equal    (zoom in)
        LEFT_TRIGGER  (ABS_Z)  → Minus    (zoom out)
        Right stick (ABS_RX/Y) → pan offset (read via .stick property)
    """

    def __init__(self, gamepad: InputDevice, window=None):
        super().__init__(daemon=True)
        self._gamepad = gamepad
        self._window = window
        self._trigger_active = {e.ABS_Z: False, e.ABS_RZ: False}
        self._stick_x = 0.0
        self._stick_y = 0.0
        self._left_y = 0.0
        try:
            self._rx_info = gamepad.absinfo(e.ABS_RX)
        except Exception:
            self._rx_info = None
        try:
            self._ry_info = gamepad.absinfo(e.ABS_RY)
        except Exception:
            self._ry_info = None
        try:
            self._ly_info = gamepad.absinfo(e.ABS_Y)
        except Exception:
            self._ly_info = None

    @property
    def stick(self) -> tuple[float, float]:
        return (self._stick_x, self._stick_y)

    @property
    def left_y(self) -> float:
        return self._left_y

    def run(self) -> None:
        for ev in self._gamepad.read_loop():
            if self._window is not None and not self._window.isActiveWindow():
                continue
            if ev.type == ecodes.EV_KEY and ev.value == 1:
                match ev.code:
                    case ecodes.BTN_EAST: _press(e.KEY_ESC)
                    case ecodes.BTN_TR:   _press(e.KEY_PAGEDOWN)
                    case ecodes.BTN_TL:   _press(e.KEY_PAGEUP)
                    case ecodes.BTN_WEST: _press(e.KEY_R)
            elif ev.type == ecodes.EV_ABS:
                match ev.code:
                    case e.ABS_RX:
                        self._stick_x = _normalize(ev.value, self._rx_info)
                    case e.ABS_RY:
                        self._stick_y = _normalize(ev.value, self._ry_info)
                    case e.ABS_Y:
                        self._left_y = _normalize(ev.value, self._ly_info)
                    case e.ABS_RZ:  # RIGHT_TRIGGER → zoom in
                        active = ev.value > _TRIGGER_THRESHOLD
                        if active and not self._trigger_active[e.ABS_RZ]:
                            _press(e.KEY_EQUAL)
                        self._trigger_active[e.ABS_RZ] = active
                    case e.ABS_Z:   # LEFT_TRIGGER → zoom out
                        active = ev.value > _TRIGGER_THRESHOLD
                        if active and not self._trigger_active[e.ABS_Z]:
                            _press(e.KEY_MINUS)
                        self._trigger_active[e.ABS_Z] = active
