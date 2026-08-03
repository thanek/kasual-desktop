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
_OSTREE_MARKER = Path("/run/ostree-booted")
_DEVICE_TREE_MODEL = Path("/proc/device-tree/model")

_CDM_GLOBS = (
    "/var/lib/widevine/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/google/chrome*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/microsoft/msedge*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/google-chrome/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.config/BraveSoftware/Brave-Browser/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/com.google.Chrome/config/google-chrome/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/org.chromium.Chromium/config/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "~/snap/chromium/common/chromium/WidevineCdm/*/_platform_specific/linux_*/libwidevinecdm.so",
    "/usr/lib*/chromium*/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    "/opt/WidevineCdm/_platform_specific/linux_*/libwidevinecdm.so",
    # Firefox's GMP updater downloads the same library. Whether Qt WebEngine
    # accepts that copy is unverified.
    "~/.mozilla/firefox/*/gmp-widevinecdm/*/libwidevinecdm.so",
)

# An architecture absent here is what the recipe layer reports as unsupported.
_ARCH_DIRS = {
    "aarch64": "linux_arm64",
    "arm64": "linux_arm64",
    "armv7l": "linux_arm",
    "x86_64": "linux_x64",
    "amd64": "linux_x64",
}


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

    def cdm_path(self) -> str | None:
        """Chrome files each component update under its own version directory,
        and those names do not sort: ``4.10.9`` sits above ``4.10.10``."""
        wanted = _ARCH_DIRS.get(platform.machine())
        if wanted is None:
            return None
        for pattern in _CDM_GLOBS:
            hits = [path for path in glob.glob(os.path.expanduser(pattern))
                    if _is_module(path, wanted)]
            if hits:
                return max(hits, key=os.path.getmtime)
        return None

    @staticmethod
    def _traits() -> tuple[str, ...]:
        """Raspberry Pi OS reports itself as plain Debian, so the board comes
        from the device tree."""
        found = []
        if _OSTREE_MARKER.exists():
            found.append("ostree")
        if "Raspberry Pi" in _device_tree_model():
            found.append("raspberrypi")
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


def _is_module(path: str, arch_dir: str) -> bool:
    """``widevine-installer`` leaves an empty ``linux_x64`` stub beside the real
    ARM module because Chromium insists on that path. A Firefox profile, in
    turn, holds one build under no architecture directory at all.

    Distro Chromium packages symlink into ``/var/lib/widevine``, so a glob hit
    can be a link that leads nowhere until the installer has run.
    """
    if "_platform_specific" in path and arch_dir not in path:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError as exc:
        logger.debug("Ignoring unreadable CDM candidate %s: %s", path, exc)
        return False


def _device_tree_model() -> str:
    try:
        return _DEVICE_TREE_MODEL.read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""
