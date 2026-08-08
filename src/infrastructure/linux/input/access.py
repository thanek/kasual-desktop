"""DeviceAccess for Linux — who may open the input nodes, read off the system.

Device nodes Kasual Desktop cannot open are exactly the ones ``evdev`` filters
out of ``list_devices()``, so enumeration cannot go through evdev here: a gamepad
is recognised from udev's own database instead, whose ``ID_INPUT_JOYSTICK`` and
``ID_INPUT_GAMEPAD`` properties are the ones the shipped rule matches on. Those
records are world-readable, so the answer does not depend on the access being
diagnosed.
"""

from __future__ import annotations

import glob
import grp
import logging
import os
import shutil
from pathlib import Path

from domain.input_access.ports import DeviceAccess, NodeAccess

logger = logging.getLogger(__name__)

UINPUT_NODE = Path("/dev/uinput")
INPUT_GROUP = "input"

_EVENT_NODES = "/dev/input/event*"
_UDEV_DATA = Path("/run/udev/data")
_JOYSTICK_PROPERTIES = ("E:ID_INPUT_JOYSTICK=1", "E:ID_INPUT_GAMEPAD=1")

_RULE_DIRECTORIES = (
    Path("/etc/udev/rules.d"),
    Path("/usr/lib/udev/rules.d"),
    Path("/lib/udev/rules.d"),
)
RULE_FILE = "99-kasual-desktop.rules"


class LinuxDeviceAccess(DeviceAccess):
    def uinput(self) -> NodeAccess:
        return _node_access(UINPUT_NODE)

    def joysticks(self) -> tuple[NodeAccess, ...]:
        return tuple(
            _node_access(node)
            for node in sorted(Path(p) for p in glob.glob(_EVENT_NODES))
            if _is_joystick(node)
        )

    def grants_joystick_access(self) -> bool:
        return self.access_rule_installed() or _in_input_group()

    def access_rule_installed(self) -> bool:
        return any((base / RULE_FILE).is_file() for base in _RULE_DIRECTORIES)

    def udev_available(self) -> bool:
        return shutil.which("udevadm") is not None


def _node_access(node: Path) -> NodeAccess:
    if not node.exists():
        return NodeAccess.MISSING
    readable_and_writable = os.access(node, os.R_OK | os.W_OK)
    return NodeAccess.GRANTED if readable_and_writable else NodeAccess.DENIED


def _is_joystick(node: Path) -> bool:
    record = _udev_record(node)
    return any(prop in record for prop in _JOYSTICK_PROPERTIES)


def _udev_record(node: Path) -> tuple[str, ...]:
    try:
        device = node.stat().st_rdev
        path = _UDEV_DATA / f"c{os.major(device)}:{os.minor(device)}"
        return tuple(path.read_text(encoding="utf-8").splitlines())
    except OSError as exc:
        logger.debug("No udev record for %s: %s", node, exc)
        return ()


def _in_input_group() -> bool:
    try:
        return grp.getgrnam(INPUT_GROUP).gr_gid in os.getgroups()
    except KeyError:
        return False
