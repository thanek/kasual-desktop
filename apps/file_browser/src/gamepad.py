"""Gamepad detection and translation its buttons to system keys."""

import threading
import time

from evdev import InputDevice, UInput, ecodes, list_devices
from evdev import ecodes as e


_ui = UInput()


def _press(key: int) -> None:
    _ui.write(e.EV_KEY, key, 1)
    _ui.write(e.EV_KEY, key, 0)
    _ui.syn()


def find_pad(names: list[str], timeout: float = 10.0) -> InputDevice:
    """Waits for gamepad with given name appearance, max timeout seconds."""
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


class PadListener(threading.Thread):
    """
    Thread that translates evdev gamepad → virtual UInput keys.

    Only forwards events when *window* is the active window — prevents double
    navigation when multiple Kasual apps run simultaneously and all share the
    same kasual-vpad virtual device.

    Mapping:
        A (BTN_SOUTH)  → Enter
        B (BTN_EAST)   → Escape
        Y (BTN_NORTH)  → H
        X (BTN_WEST)   → U
        L1 (BTN_TL)    → Backspace
        R1 (BTN_TR)    → F
        D-pad          → arrows
    """

    def __init__(self, gamepad: InputDevice, window=None):
        super().__init__(daemon=True)
        self._gamepad = gamepad
        self._window = window

    def run(self) -> None:
        for ev in self._gamepad.read_loop():
            if self._window is not None and not self._window.isActiveWindow():
                continue
            if ev.type == ecodes.EV_KEY and ev.value == 1:
                match ev.code:
                    case ecodes.BTN_SOUTH: _press(e.KEY_ENTER)
                    case ecodes.BTN_EAST:  _press(e.KEY_ESC)
                    case ecodes.BTN_NORTH: _press(e.KEY_H)
                    case ecodes.BTN_WEST:  _press(e.KEY_U)
                    case ecodes.BTN_TL:    _press(e.KEY_BACKSPACE)
                    case ecodes.BTN_TR:    _press(e.KEY_F)
            elif ev.type == ecodes.EV_ABS:
                match ev.code:
                    case ecodes.ABS_HAT0X:
                        if ev.value == -1:  _press(e.KEY_LEFT)
                        elif ev.value == 1: _press(e.KEY_RIGHT)
                    case ecodes.ABS_HAT0Y:
                        if ev.value == -1:  _press(e.KEY_UP)
                        elif ev.value == 1: _press(e.KEY_DOWN)
