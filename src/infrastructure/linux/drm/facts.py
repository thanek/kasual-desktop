"""SystemFacts for Linux.

``apps/netflix`` keeps its own copy of these globs — bundled apps run as
standalone processes against the system Python and import nothing from ``src``,
so the two lists must be changed together.
"""

from __future__ import annotations

import glob
import logging
import os
import platform
import shutil
from pathlib import Path

from domain.drm.plan import MachineProfile
from domain.drm.ports import SystemFacts

logger = logging.getLogger(__name__)

_OS_RELEASE = Path("/etc/os-release")

_CDM_GLOBS = (
    "/var/lib/widevine/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/google/chrome/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/google-chrome/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "/usr/lib*/chromium*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
)

_ARCH_DIRS = {"aarch64": "linux_arm64", "arm64": "linux_arm64"}


class LinuxSystemFacts(SystemFacts):
    def machine(self) -> MachineProfile:
        os_release = self._os_release()
        return MachineProfile(
            arch=platform.machine(),
            distro_id=os_release.get("ID", ""),
            like=tuple(os_release.get("ID_LIKE", "").split()),
        )

    def has_command(self, name: str) -> bool:
        return shutil.which(name) is not None

    def path_exists(self, pattern: str) -> bool:
        return bool(glob.glob(os.path.expanduser(pattern)))

    def cdm_path(self) -> str | None:
        """The newest module for this architecture. ``widevine-installer``
        leaves an empty ``linux_x64`` stub beside the real ARM one because
        Chromium insists on that path, hence the size test."""
        wanted = _ARCH_DIRS.get(platform.machine(), "linux_x64")
        for pattern in _CDM_GLOBS:
            hits = sorted(
                path for path in glob.glob(os.path.expanduser(pattern))
                if wanted in path and os.path.getsize(path) > 0
            )
            if hits:
                return hits[-1]
        return None

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
