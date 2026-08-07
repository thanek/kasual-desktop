"""Virtual keyboard for behavioral tests — an evdev UInput device with the keys
Kasual Desktop navigates by, delivered through the compositor like a real one's.
"""

import time

from evdev import UInput, ecodes as e

NAME = 'behavioral-test-keyboard'

_UDEV_SETTLE_S = 0.5
_HOLD_S = 0.08
_BETWEEN_PRESSES_S = 0.15

_KEEPS_KASUAL_DESKTOP_FROM_GRABBING_THIS = e.KEY_A
_NAVIGATION_KEYS = [
    e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_ENTER, e.KEY_ESC,
]

_CAPABILITIES = {
    e.EV_KEY: [_KEEPS_KASUAL_DESKTOP_FROM_GRABBING_THIS, *_NAVIGATION_KEYS],
}


class VirtualKeyboard:
    def __init__(self) -> None:
        self._ui = UInput(_CAPABILITIES, name=NAME)
        self.presses: list[dict] = []
        time.sleep(_UDEV_SETTLE_S)

    @property
    def device_path(self) -> str:
        return getattr(self._ui.device, 'path', '?')

    def close(self) -> None:
        if self._ui is not None:
            self._ui.close()
            self._ui = None

    def press(self, key: int) -> None:
        self.presses.append({'at': time.time(), 'press': e.KEY[key]})
        self._ui.write(e.EV_KEY, key, 1)
        self._ui.syn()
        time.sleep(_HOLD_S)
        self._ui.write(e.EV_KEY, key, 0)
        self._ui.syn()
        time.sleep(_BETWEEN_PRESSES_S)

    def left(self) -> None:
        self.press(e.KEY_LEFT)

    def right(self) -> None:
        self.press(e.KEY_RIGHT)

    def up(self) -> None:
        self.press(e.KEY_UP)

    def down(self) -> None:
        self.press(e.KEY_DOWN)
