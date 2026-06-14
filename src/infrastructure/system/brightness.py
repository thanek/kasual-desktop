"""BrightnessControl adapters — one per mechanism a desktop may expose.

Why several (unlike volume's single pactl adapter): screen brightness has no
single portable interface. Laptops expose a kernel backlight (sysfs, driven here
via ``brightnessctl``); KDE Plasma offers a D-Bus PowerManagement service; a
desktop with an external monitor may have no controllable backlight at all. Each
adapter implements the same :class:`BrightnessControl` port;
:func:`select_brightness_control` picks the first one usable on the running
system, so the overlay, top-bar button and action catalog stay oblivious to
which DE-specific backend is in play.
"""

import logging
import shutil
import subprocess

from domain.system.brightness import Brightness, BrightnessControl

logger = logging.getLogger(__name__)

# Qt 6 ships the tool as ``qdbus6``; the unsuffixed ``qdbus`` is often a broken
# Qt-version-selector wrapper ("could not find a Qt installation"). Prefer the
# suffixed binary, falling back only if it is absent.
_QDBUS_BINARIES = ("qdbus6", "qdbus")


def _qdbus_binary() -> str | None:
    for name in _QDBUS_BINARIES:
        if shutil.which(name):
            return name
    return None


class BrightnessctlBrightnessControl(BrightnessControl):
    """Generic, DE-agnostic adapter over the ``brightnessctl`` CLI."""

    def get(self) -> Brightness:
        try:
            out = subprocess.check_output(
                ["brightnessctl", "-m"],  # machine-readable: name,class,current,percent,max
                text=True, stderr=subprocess.DEVNULL,
            )
            # First device line, e.g. "intel_backlight,backlight,512,40%,1000".
            percent = out.strip().splitlines()[0].split(",")[3]
            return Brightness(int(percent.rstrip("%")))
        except Exception:
            return Brightness(Brightness.DEFAULT)

    def set(self, brightness: Brightness) -> None:
        try:
            subprocess.Popen(
                ["brightnessctl", "set", f"{brightness.value}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("Error during brightness setting: %s", exc)


class KdeBrightnessControl(BrightnessControl):
    """Adapter over KDE Plasma's PowerManagement D-Bus service via ``qdbus``.

    PowerManagement reports brightness as an absolute value against a maximum, so
    the conversion to/from the 0–100 domain scale happens here."""

    _SERVICE = "org.kde.Solid.PowerManagement"
    _PATH    = "/org/kde/Solid/PowerManagement/Actions/BrightnessControl"
    _IFACE   = "org.kde.Solid.PowerManagement.Actions.BrightnessControl"

    def __init__(self, qdbus: str = "qdbus6") -> None:
        self._qdbus = qdbus

    def get(self) -> Brightness:
        try:
            current = int(self._call("brightness"))
            maximum = int(self._call("brightnessMax"))
            if maximum <= 0:
                return Brightness(Brightness.DEFAULT)
            return Brightness(round(current * 100 / maximum))
        except Exception:
            return Brightness(Brightness.DEFAULT)

    def set(self, brightness: Brightness) -> None:
        try:
            maximum = int(self._call("brightnessMax"))
            absolute = round(brightness.value * maximum / 100)
            subprocess.Popen(
                [self._qdbus, self._SERVICE, self._PATH,
                 f"{self._IFACE}.setBrightnessSilent", str(absolute)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("Error during brightness setting: %s", exc)

    def _call(self, method: str) -> str:
        return subprocess.check_output(
            [self._qdbus, self._SERVICE, self._PATH, f"{self._IFACE}.{method}"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()


class NullBrightnessControl(BrightnessControl):
    """No-op fallback for systems with no controllable backlight (e.g. a desktop
    on an external monitor). Reports a fixed level and ignores changes, so the UI
    degrades gracefully instead of erroring."""

    def get(self) -> Brightness:
        return Brightness(Brightness.DEFAULT)

    def set(self, brightness: Brightness) -> None:
        pass


def select_brightness_control() -> BrightnessControl:
    """Pick the best available BrightnessControl for the running system.

    Prefers a real kernel backlight via ``brightnessctl`` (works under any DE),
    then KDE's D-Bus service, and finally a no-op fallback. This is the single
    DE-dependent decision; everything upstream depends only on the port."""
    if shutil.which("brightnessctl"):
        return BrightnessctlBrightnessControl()
    qdbus = _qdbus_binary()
    if qdbus:
        return KdeBrightnessControl(qdbus)
    logger.warning("No brightness backend available; brightness control disabled")
    return NullBrightnessControl()
