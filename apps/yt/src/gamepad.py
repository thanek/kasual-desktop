"""Gamepad input for File Browser — context-aware: browse mode and media mode.

Platform-dispatched: on Linux reads the virtual ``kasual-vpad`` evdev device and
emits keyboard events via UInput; on Windows reads the controller via pygame and
emits keyboard events via Win32 SendInput. The browse/media mode mapping is
platform-agnostic (string button codes + Key constants from keyinput).
"""

import threading

from keyinput import Key, press
from padbackend import (
    ABS_HAT0X, ABS_HAT0Y, ABS_RY, ABS_RX, ABS_RZ, ABS_Y, ABS_Z,
    BTN_EAST, BTN_NORTH, BTN_SOUTH, BTN_TL, BTN_TR, BTN_WEST,
    PadListener as _PadListener, find_pad,
)

_TRIGGER_THRESHOLD = 200   # evdev LT/RT raw value (0..255)
_PG_TRIGGER_THRESHOLD = 0.3  # pygame LT/RT normalized (0..1)
_REPEAT_DELAY = 0.35
_REPEAT_INTERVAL = 0.08
_IS_WINDOWS = __import__("sys").platform == "win32"


class PadListener(_PadListener):
    """Context-aware gamepad translator — browse mode and media mode.

    Browse mode:
        A (BTN_SOUTH)  → Enter
        B (BTN_EAST)   → Escape
        Y (BTN_NORTH)  → H
        X (BTN_WEST)   → S   (sort menu)
        LB (BTN_TL)    → Up   (prev item)
        RB (BTN_TR)    → Down (next item)
        LT (ABS_Z)     → Up   (prev item)
        RT (ABS_RZ)    → Down (next item)
        D-pad          → arrows

    Media mode:
        B  (BTN_EAST)  → Escape    (exit / reset zoom)
        LB (BTN_TL)    → Page Up   (prev file)
        RB (BTN_TR)    → Page Down (next file)
        X  (BTN_WEST)  → R         (rotate CW, image mode)
        LT (ABS_Z)     → Minus     (zoom out, image mode)
        RT (ABS_RZ)    → Equal     (zoom in, image mode)
        Right stick    → pan       (.stick property, image mode)
        Left stick Y   → zoom      (.left_y property, image mode)
    """

    def __init__(self, gamepad, window=None):
        super().__init__(gamepad, window=window)
        self._trigger_active = {ABS_Z: False, ABS_RZ: False}
        self._repeat_stop: threading.Event | None = None

    def set_mode(self, mode: str) -> None:
        super().set_mode(mode)
        self._trigger_active = {ABS_Z: False, ABS_RZ: False}
        self._stop_repeat()

    def _start_repeat(self, key) -> None:
        self._stop_repeat()
        stop = threading.Event()
        self._repeat_stop = stop

        def _loop():
            if stop.wait(timeout=_REPEAT_DELAY):
                return
            while not stop.is_set():
                press(key)
                stop.wait(timeout=_REPEAT_INTERVAL)

        threading.Thread(target=_loop, daemon=True).start()

    def _stop_repeat(self) -> None:
        if self._repeat_stop is not None:
            self._repeat_stop.set()
            self._repeat_stop = None

    # ── App-facing hooks ─────────────────────────────────────────────────────

    def on_key(self, code: str) -> None:
        if self._mode == "browse":
            if   code == BTN_SOUTH: press(Key.KEY_ENTER)
            elif code == BTN_EAST:  press(Key.KEY_ESC)
            elif code == BTN_NORTH: press(Key.KEY_H)
            elif code == BTN_WEST:  press(Key.KEY_S)
            elif code == BTN_TL:    press(Key.KEY_UP)
            elif code == BTN_TR:    press(Key.KEY_DOWN)
        else:  # media mode
            if   code == BTN_SOUTH: press(Key.KEY_ENTER)
            elif code == BTN_EAST:  press(Key.KEY_ESC)
            elif code == BTN_NORTH: press(Key.KEY_H)
            elif code == BTN_WEST:  press(Key.KEY_R)
            elif code == BTN_TL:    press(Key.KEY_PAGEUP)
            elif code == BTN_TR:    press(Key.KEY_PAGEDOWN)

    def on_axis(self, code: str, value, prev) -> None:
        if self._mode == "browse":
            self._on_axis_browse(code, value, prev)
        else:
            self._on_axis_media(code, value, prev)

    def _on_axis_browse(self, code: str, value, prev) -> None:
        if   code == ABS_HAT0X:
            if self._hat_left(value):
                press(Key.KEY_LEFT);  self._start_repeat(Key.KEY_LEFT)
            elif self._hat_right(value):
                press(Key.KEY_RIGHT); self._start_repeat(Key.KEY_RIGHT)
            else:
                self._stop_repeat()
        elif code == ABS_HAT0Y:
            if self._hat_up(value):
                press(Key.KEY_UP);   self._start_repeat(Key.KEY_UP)
            elif self._hat_down(value):
                press(Key.KEY_DOWN); self._start_repeat(Key.KEY_DOWN)
            else:
                self._stop_repeat()
        elif code == ABS_Z:
            active = self._trigger_pressed(value)
            if active and not self._trigger_active[ABS_Z]:
                press(Key.KEY_UP)
            self._trigger_active[ABS_Z] = active
        elif code == ABS_RZ:
            active = self._trigger_pressed(value)
            if active and not self._trigger_active[ABS_RZ]:
                press(Key.KEY_DOWN)
            self._trigger_active[ABS_RZ] = active

    def _on_axis_media(self, code: str, value, prev) -> None:
        if   code == ABS_HAT0X:
            if self._hat_left(value):
                press(Key.KEY_LEFT);  self._start_repeat(Key.KEY_LEFT)
            elif self._hat_right(value):
                press(Key.KEY_RIGHT); self._start_repeat(Key.KEY_RIGHT)
            else:
                self._stop_repeat()
        elif code == ABS_Z:
            active = self._trigger_pressed(value)
            if active and not self._trigger_active[ABS_Z]:
                press(Key.KEY_MINUS)
            self._trigger_active[ABS_Z] = active
        elif code == ABS_RZ:
            active = self._trigger_pressed(value)
            if active and not self._trigger_active[ABS_RZ]:
                press(Key.KEY_EQUAL)
            self._trigger_active[ABS_RZ] = active

    # ── Axis value interpretation (platform-normalised) ──────────────────────
    # D-pad: evdev gives -1/0/1, pygame gives -1/0/1 — same convention.
    # Triggers: evdev gives 0..255, pygame gives 0..1 (with sign flip on some
    # drivers, hence the abs()). The thresholds are platform-specific.

    @staticmethod
    def _hat_left(value) -> bool:
        return value < 0

    @staticmethod
    def _hat_right(value) -> bool:
        return value > 0

    @staticmethod
    def _hat_up(value) -> bool:
        return value < 0

    @staticmethod
    def _hat_down(value) -> bool:
        return value > 0

    @staticmethod
    def _trigger_pressed(value) -> bool:
        if _IS_WINDOWS:
            # pygame XInput: triggers are -1 (rest) .. 1 (pressed).
            return value > _PG_TRIGGER_THRESHOLD
        # evdev: triggers are 0..255.
        return value > _TRIGGER_THRESHOLD
