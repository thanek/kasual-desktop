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

from PyQt6.QtCore import QTimer

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

    def is_controllable(self) -> bool:
        """True only if a *backlight*-class device exists.

        ``brightnessctl`` is present on plenty of desktops that have no panel
        backlight (it then falls back to LED devices), so the binary's presence
        isn't enough — we query the backlight class explicitly and treat an empty
        list as 'no controllable backlight'."""
        try:
            out = subprocess.check_output(
                ["brightnessctl", "-lm", "-c", "backlight"],
                text=True, stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False
        return any(
            line.split(",")[1:2] == ["backlight"]
            for line in out.splitlines() if line.strip()
        )


class _DebouncedBrightnessControl(BrightnessControl):
    """Base for adapters with an expensive write: a slider drag emits a tick per
    pixel, and only the last one is worth applying."""

    _DEBOUNCE_MS = 50

    def __init__(self) -> None:
        self._pending: Brightness | None = None
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self._DEBOUNCE_MS)
        self._debounce.timeout.connect(self._flush)

    def set(self, brightness: Brightness) -> None:
        self._pending = brightness
        self._debounce.start()

    def _flush(self) -> None:
        brightness, self._pending = self._pending, None
        if brightness is None:
            return
        try:
            self._apply(brightness)
        except Exception as exc:
            logger.error("Error during brightness setting: %s", exc)

    def _apply(self, brightness: Brightness) -> None:
        raise NotImplementedError


class KdeBrightnessControl(_DebouncedBrightnessControl):
    """Adapter over KDE Plasma's PowerManagement D-Bus service via ``qdbus``.

    PowerManagement reports brightness as an absolute value against a maximum, so
    the conversion to/from the 0–100 domain scale happens here."""

    _SERVICE = "org.kde.Solid.PowerManagement"
    _PATH    = "/org/kde/Solid/PowerManagement/Actions/BrightnessControl"
    _IFACE   = "org.kde.Solid.PowerManagement.Actions.BrightnessControl"

    def __init__(self, qdbus: str = "qdbus6") -> None:
        super().__init__()
        self._qdbus = qdbus
        self._max: int | None = None   # brightnessMax is fixed for the session

    def get(self) -> Brightness:
        try:
            current = int(self._call("brightness"))
            maximum = self._brightness_max()
            if maximum <= 0:
                return Brightness(Brightness.DEFAULT)
            return Brightness(round(current * 100 / maximum))
        except Exception:
            return Brightness(Brightness.DEFAULT)

    def _apply(self, brightness: Brightness) -> None:
        absolute = round(brightness.value * self._brightness_max() / 100)
        subprocess.Popen(
            [self._qdbus, self._SERVICE, self._PATH,
             f"{self._IFACE}.setBrightnessSilent", str(absolute)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def is_controllable(self) -> bool:
        """True if PowerManagement reports a positive maximum brightness.

        A Plasma session driving only an external monitor with no controllable
        backlight reports a zero (or unavailable) maximum — treated as 'no
        controllable backlight'."""
        try:
            return self._brightness_max() > 0
        except Exception:
            return False

    def _brightness_max(self) -> int:
        if self._max is None:
            self._max = int(self._call("brightnessMax"))
        return self._max

    def _call(self, method: str) -> str:
        return subprocess.check_output(
            [self._qdbus, self._SERVICE, self._PATH, f"{self._IFACE}.{method}"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()


class DdcutilBrightnessControl(_DebouncedBrightnessControl):
    """Adapter driving an external monitor's own backlight over DDC/CI — the only
    mechanism that reaches a desktop monitor outside Plasma."""

    _BRIGHTNESS_VCP = "10"
    _DISPLAY = "1"

    _DEBOUNCE_MS = 150

    def __init__(self) -> None:
        super().__init__()
        self._controllable: bool | None = None

    def get(self) -> Brightness:
        reading = self._read()
        if reading is None:
            return Brightness(Brightness.DEFAULT)
        current, maximum = reading
        return Brightness(round(current * 100 / maximum))

    def _apply(self, brightness: Brightness) -> None:
        subprocess.Popen(
            [*self._command("setvcp"), str(brightness.value)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def is_controllable(self) -> bool:
        if self._controllable is None:
            self._controllable = self._read() is not None
        return self._controllable

    def _read(self) -> tuple[int, int] | None:
        try:
            out = subprocess.check_output(
                self._command("getvcp"), text=True, stderr=subprocess.DEVNULL,
            )
            # "VCP 10 C <current> <max>"
            _, _, kind, current, maximum = out.split()
        except Exception:
            return None
        if kind != "C" or int(maximum) <= 0:
            return None
        return int(current), int(maximum)

    def _command(self, verb: str) -> list[str]:
        return ["ddcutil", verb, "--display", self._DISPLAY, "--brief",
                self._BRIGHTNESS_VCP]


class NullBrightnessControl(BrightnessControl):
    """No-op fallback for systems with no controllable backlight (e.g. a desktop
    on an external monitor). Reports a fixed level and ignores changes, so the UI
    degrades gracefully instead of erroring."""

    def get(self) -> Brightness:
        return Brightness(Brightness.DEFAULT)

    def set(self, brightness: Brightness) -> None:
        pass

    def is_controllable(self) -> bool:
        return False


def select_brightness_control() -> BrightnessControl:
    """Pick the best available BrightnessControl for the running system.

    Prefers a real kernel backlight via ``brightnessctl`` (works under any DE),
    then KDE's D-Bus service, then DDC/CI straight to an external monitor, and
    finally a no-op fallback. An installed backend that drives nothing on this
    host is skipped rather than shadowing the next one: ``brightnessctl`` ships as
    a package dependency even on desktops whose only adjustable screen is an
    external monitor. DDC ranks last because its probe costs an I2C round trip.
    This is the single DE-dependent decision; everything upstream depends only on
    the port."""
    candidates: list[BrightnessControl] = []
    if shutil.which("brightnessctl"):
        candidates.append(BrightnessctlBrightnessControl())
    qdbus = _qdbus_binary()
    if qdbus:
        candidates.append(KdeBrightnessControl(qdbus))
    if shutil.which("ddcutil"):
        candidates.append(DdcutilBrightnessControl())
    for control in candidates:
        if control.is_controllable():
            return control
    logger.warning("No brightness backend available; brightness control disabled")
    return NullBrightnessControl()
