"""SystemFacts for Linux — what a recipe may ask about the machine itself."""

from __future__ import annotations

import glob
import logging
import os
import platform
import shutil
from pathlib import Path

from domain.setup.plan import MachineProfile
from domain.setup.ports import SystemFacts

logger = logging.getLogger(__name__)

_OS_RELEASE = Path("/etc/os-release")
_OSTREE_MARKER = Path("/run/ostree-booted")
_DEVICE_TREE_MODEL = Path("/proc/device-tree/model")

OSTREE = "ostree"
RASPBERRY_PI = "raspberrypi"


class LinuxSystemFacts(SystemFacts):
    def machine(self) -> MachineProfile:
        os_release = self._os_release()
        return MachineProfile(
            arch=platform.machine(),
            distro_id=os_release.get("ID", ""),
            like=tuple(os_release.get("ID_LIKE", "").split()),
            traits=self._traits(),
        )

    def has_command(self, name: str) -> bool:
        return shutil.which(name) is not None

    def path_exists(self, pattern: str) -> bool:
        return bool(glob.glob(os.path.expanduser(pattern)))

    @staticmethod
    def _traits() -> tuple[str, ...]:
        found = []
        if _OSTREE_MARKER.exists():
            found.append(OSTREE)
        if "Raspberry Pi" in _device_tree_model():
            found.append(RASPBERRY_PI)
        return tuple(found)

    @staticmethod
    def _os_release() -> dict[str, str]:
        try:
            text = _OS_RELEASE.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("Cannot read %s: %s", _OS_RELEASE, exc)
            return {}
        fields = {}
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                fields[key.strip()] = value.strip().strip('"').strip("'")
        return fields


def _device_tree_model() -> str:
    """Raspberry Pi OS reports itself as plain Debian, so the board is only
    visible in the device tree."""
    try:
        return _DEVICE_TREE_MODEL.read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""
