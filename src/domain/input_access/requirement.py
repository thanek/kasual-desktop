"""The two device nodes Kasual Desktop opens to run a gamepad.

Reading the pad needs the joystick's ``/dev/input/event*`` node; forwarding it to
the app underneath needs ``/dev/uinput``, and a grab that cannot build the
virtual pad is rolled back — so a system that withholds either node reports no
gamepad at all rather than a broken one.
"""

from dataclasses import dataclass

from domain.input_access.ports import DeviceAccess, NodeAccess
from domain.setup.plan import Assessment, Check, StatusLine, Subject
from domain.setup.ports import Requirement
from domain.shared.i18n import translate

ACCESS = "access"
UINPUT = "uinput"
DEVICES = "devices"

UINPUT_NODE = Check(ACCESS, UINPUT)
JOYSTICK_NODES = Check(ACCESS, DEVICES)

RULE_INSTALLED = "kasual-access-rule"
NO_UDEV = "no-udev"


@dataclass(frozen=True)
class _Reading:
    """One look at the device nodes. Every question the report asks is answered
    from the same look — scanning /dev/input means a stat and a udev record per
    node, and the report asks several times over."""

    uinput: NodeAccess
    joysticks: tuple[NodeAccess, ...]
    granted: bool

    @property
    def joysticks_readable(self) -> bool:
        if not self.joysticks:
            return self.granted
        return all(node is NodeAccess.GRANTED for node in self.joysticks)


class GamepadAccess(Requirement):
    def __init__(self, access: DeviceAccess) -> None:
        self._access = access
        self._reading = self._read()

    def subject(self) -> Subject:
        return Subject(
            title=translate(
                "Kasual Desktop", "Kasual Desktop needs direct gamepad access"),
            unsupported=translate(
                "Kasual Desktop",
                "Kasual Desktop has no recipe for granting gamepad access on this "
                "system. Everything else works; only the controller stays "
                "unavailable until you grant it yourself.",
            ),
        )

    def assess(self) -> Assessment:
        self._reading = self._read()
        return Assessment(
            (self._joystick_status(), self._uinput_status()), self._traits())

    def satisfied(self, check: Check) -> bool:
        if check == JOYSTICK_NODES:
            return self._reading.joysticks_readable
        if check == UINPUT_NODE:
            return self._reading.uinput is NodeAccess.GRANTED
        return False

    def _read(self) -> _Reading:
        return _Reading(
            uinput=self._access.uinput(),
            joysticks=tuple(self._access.joysticks()),
            granted=self._access.grants_joystick_access(),
        )

    def _traits(self) -> tuple[str, ...]:
        found = []
        if self._access.access_rule_installed():
            found.append(RULE_INSTALLED)
        if not self._access.udev_available():
            found.append(NO_UDEV)
        return tuple(found)

    def _joystick_status(self) -> StatusLine:
        if self._reading.joysticks_readable:
            return StatusLine(
                translate("Kasual Desktop", "Kasual Desktop can read your gamepad"),
                met=True,
            )
        if self._reading.joysticks:
            return StatusLine(
                translate(
                    "Kasual Desktop",
                    "Kasual Desktop cannot read the connected gamepad"),
                met=False,
                detail=translate(
                    "Kasual Desktop",
                    "The controller is plugged in, but its device node is closed "
                    "to this user. Kasual Desktop skips what it cannot open, so "
                    "the controller does not show up as connected at all.",
                ),
            )
        return StatusLine(
            translate("Kasual Desktop", "Nothing here grants gamepad access"),
            met=False,
            detail=translate(
                "Kasual Desktop",
                "No controller is connected, so this cannot be tested directly. "
                "Neither the Kasual Desktop access rule nor membership of the "
                "input group is in place, though, so one you plug in now would "
                "stay invisible.",
            ),
        )

    def _uinput_status(self) -> StatusLine:
        node = self._reading.uinput
        if node is NodeAccess.GRANTED:
            return StatusLine(
                translate(
                    "Kasual Desktop",
                    "Kasual Desktop can pass the gamepad on to your apps"),
                met=True,
            )
        forwarding = translate(
            "Kasual Desktop",
            "Kasual Desktop holds the controller exclusively and forwards it to "
            "the app you launch through a virtual gamepad. Without /dev/uinput it "
            "cannot build one, and lets the controller go instead.",
        )
        if node is NodeAccess.MISSING:
            return StatusLine(
                translate("Kasual Desktop", "/dev/uinput is not there"),
                met=False,
                detail=f"{forwarding}\n\n" + translate(
                    "Kasual Desktop",
                    "The kernel module that provides it is not loaded.",
                ),
            )
        return StatusLine(
            translate("Kasual Desktop", "/dev/uinput is closed to this user"),
            met=False,
            detail=forwarding,
        )
