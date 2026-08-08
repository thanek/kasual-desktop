"""How this system hands input devices to the user Kasual Desktop runs as."""

import enum
from typing import Protocol


class NodeAccess(enum.Enum):
    GRANTED = "granted"
    DENIED = "denied"
    MISSING = "missing"


class DeviceAccess(Protocol):
    def uinput(self) -> NodeAccess:
        """Whether the virtual-gamepad node can be opened for reading and writing."""
        ...

    def joysticks(self) -> tuple[NodeAccess, ...]:
        """One entry per gamepad the kernel currently knows about — empty when
        none is connected, which says nothing about access either way."""
        ...

    def grants_joystick_access(self) -> bool:
        """Whether anything on this system would open a gamepad to this user.
        The only answer available while no gamepad is connected."""
        ...

    def access_rule_installed(self) -> bool: ...

    def udev_available(self) -> bool: ...
