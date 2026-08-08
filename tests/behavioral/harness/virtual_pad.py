"""Virtual gamepad for behavioral tests — an evdev UInput device shaped like an
Xbox 360 pad, so it passes GamepadWatcher._is_gamepad (gamepad buttons, a hat,
no KEY_A).

Steam never reads this device: KD grabs it exclusively and re-emits it as
`kasual-vpad`, and that is the pad every launched application sees. (Steam does
*notice* it, takes the X360 vendor/product ids at face value, and logs a
`hid_read failure` when the hidraw node a real X360 pad would have is not there.
Harmless, but it is why those ids are not evidence of anything.)

KD grabs whichever matching device it finds first, so physical pads must stay
disconnected. It picks this one up on its device scan, whether it was already
running or not. The name must stay distinct from KD's own re-emitter
("kasual-vpad").
"""

import time

from evdev import AbsInfo, UInput, ecodes as e

NAME = 'behavioral-test-pad'

_STICK = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
_TRIGGER = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
_HAT = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

_CAPABILITIES = {
    e.EV_KEY: [
        e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST,
        e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
        e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR,
    ],
    e.EV_ABS: [
        (e.ABS_X, _STICK), (e.ABS_Y, _STICK),
        (e.ABS_RX, _STICK), (e.ABS_RY, _STICK),
        (e.ABS_Z, _TRIGGER), (e.ABS_RZ, _TRIGGER),
        (e.ABS_HAT0X, _HAT), (e.ABS_HAT0Y, _HAT),
    ],
}


class VirtualPad:
    def __init__(self) -> None:
        self._ui = UInput(
            _CAPABILITIES, name=NAME,
            vendor=0x045e, product=0x028e, version=0x110,
        )
        # Every press, for the artifact: "the press did nothing" is only a claim until
        # it can be lined up against what the app said before and after it.
        self.presses: list[dict] = []
        # udev needs a beat to create the node before anyone can scan it
        time.sleep(0.5)

    def _record(self, what: str) -> None:
        self.presses.append({'at': time.time(), 'press': what})

    @staticmethod
    def _name(code: int, table: dict) -> str:
        name = table.get(code, code)
        return name[-1] if isinstance(name, list) else str(name)

    @property
    def device_path(self) -> str:
        return getattr(self._ui.device, 'path', '?')

    def close(self) -> None:
        """Unplugging the pad is also how the teardown minimizes KD, so this runs
        once from there and again from the run's finally."""
        if self._ui is not None:
            self._ui.close()
            self._ui = None

    # ── buttons ──────────────────────────────────────────────────────────────

    def hold(self, button: int, seconds: float) -> None:
        self._record(f'{self._name(button, e.BTN)} for {seconds}s')
        self._ui.write(e.EV_KEY, button, 1)
        self._ui.syn()
        time.sleep(seconds)
        self._ui.write(e.EV_KEY, button, 0)
        self._ui.syn()

    def press(self, button: int, hold_s: float = 0.08) -> None:
        self.hold(button, hold_s)
        time.sleep(0.15)

    def confirm(self) -> None:
        self.press(e.BTN_SOUTH)

    def back(self) -> None:
        self.press(e.BTN_EAST)

    def tile_menu(self) -> None:
        self.press(e.BTN_WEST)

    def home(self) -> None:
        """A short press — KD keeps the *hold* for itself over an app that asked for
        HOLD_1S, so this one is the app's (in Steam: its main menu)."""
        self.press(e.BTN_MODE)

    def hold_home(self, seconds: float = 1.2) -> None:
        self.hold(e.BTN_MODE, seconds)

    # ── d-pad (hat) ──────────────────────────────────────────────────────────

    def _hat(self, axis: int, direction: int) -> None:
        self._record(f'{self._name(axis, e.ABS)} {direction:+d}')
        self._ui.write(e.EV_ABS, axis, direction)
        self._ui.syn()
        time.sleep(0.08)
        self._ui.write(e.EV_ABS, axis, 0)
        self._ui.syn()
        time.sleep(0.15)

    def left(self) -> None:
        self._hat(e.ABS_HAT0X, -1)

    def right(self) -> None:
        self._hat(e.ABS_HAT0X, 1)

    def up(self) -> None:
        self._hat(e.ABS_HAT0Y, -1)

    def down(self) -> None:
        self._hat(e.ABS_HAT0Y, 1)
