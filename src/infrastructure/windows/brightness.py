"""Windows display-brightness control (the BrightnessControl port).

Two backends, probed once at construction:
  1. ``screen_brightness_control`` (sbc) — real backlight via WMI (laptop
     panels) or DDC/CI (external monitors). Used when sbc can actually read
     the current level; some desktop monitors report a DDC/CI device but raise
     ``ScreenBrightnessError`` on every call (e.g. a Samsung Generic Monitor
     with a broken DDC/CI implementation).
  2. Gamma-ramp fallback via Win32 ``SetDeviceGammaRamp`` — a visual dimming
     LUT adjustment that works on every display. Not true backlight control
     (highlights are clamped at lower levels), but the only viable option when
     sbc doesn't work on the attached monitor. The LUT resets to identity
     (100 %) on reboot, sleep, or display reconfiguration.
"""

import ctypes
import logging
from ctypes import wintypes

from domain.system.brightness import Brightness, BrightnessControl

logger = logging.getLogger(__name__)


class _SbcBrightnessControl(BrightnessControl):
    """Real backlight control via screen_brightness_control."""

    def __init__(self, current: int) -> None:
        self._current = current

    def get(self) -> Brightness:
        try:
            import screen_brightness_control as sbc
            values = sbc.get_brightness()
            if values:
                self._current = int(values[0])
        except Exception as exc:
            logger.warning("Brightness get failed (sbc): %s", exc)
        return Brightness(self._current)

    def set(self, brightness: Brightness) -> None:
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(brightness.value)
            self._current = brightness.value
        except Exception as exc:
            logger.warning("Brightness set failed (sbc): %s", exc)


# ── Gamma-ramp fallback ──────────────────────────────────────────────────────


class _GammaRamp(ctypes.Structure):
    """Win32 RAMP struct — three 256-entry WORD LUTs (R, G, B)."""
    _fields_ = [
        ("red", ctypes.c_ushort * 256),
        ("green", ctypes.c_ushort * 256),
        ("blue", ctypes.c_ushort * 256),
    ]


# Win32 bindings used by the gamma-ramp fallback. Set up once at import.
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.POINTER(_GammaRamp)]
gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL
# CreateDCW(device_name, None, None, None) → HDC for a specific monitor.
gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def _collect_monitor_dcs() -> list:
    """Return a DC per physical monitor via ``EnumDisplayMonitors``+``CreateDCW``.

    ``GetDC(0)`` only reaches the primary adapter's LUT, so on multi-monitor
    setups split across GPUs it leaves the secondary display untouched. This
    walker gives each monitor its own DC so the ramp reaches every display.
    """
    dcs: list = []

    EnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p
    )

    def _cb(_hmon, _hdc, _rect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(_hmon, ctypes.byref(info)):
            dc = gdi32.CreateDCW(info.szDevice, None, None, None)
            if dc:
                dcs.append(dc)
        return True

    try:
        user32.EnumDisplayMonitors(0, None, EnumProc(_cb), 0)
    except Exception as exc:
        logger.warning("EnumDisplayMonitors failed: %s", exc)
    return dcs


def _build_ramp(percent: int) -> _GammaRamp:
    """Power-curve gamma ramp for *percent* (0..100).

    A linear scale (``i * 257 * factor``) is rejected by several display
    drivers below ~50 % (anti-blackout protection clamps the steepest LUTs).
    A power curve — ``val = (i/255)^gamma * 65535`` with ``gamma = 100/percent``
    — reaches far darker levels before the driver rejects it, because it keeps
    the upper end of the LUT intact and only flattens the dark section.
    """
    ramp = _GammaRamp()
    p = max(1, min(100, percent))
    gamma = 100.0 / p   # 100 % → 1.0 (identity), 50 % → 2.0, 25 % → 4.0
    for i in range(256):
        val = int(round((i / 255.0) ** gamma * 65535))
        ramp.red[i] = val
        ramp.green[i] = val
        ramp.blue[i] = val
    return ramp


class _GammaRampBrightnessControl(BrightnessControl):
    """Visual dimming via the Win32 gamma ramp (display LUT).

    Works on every display — including desktop monitors / TVs where DDC/CI is
    broken or unsupported (e.g. an HDMI TV with no CEC). At lower levels the
    LUT is scaled linearly so the monitor emits less light (highlights clamp).
    The ramp resets to the identity LUT (100 %) on reboot, sleep, or display
    reconfiguration, so the dimming never persists past the Windows session.

    Multi-monitor: enumerates every display via ``EnumDisplayMonitors`` and
    applies the ramp to each monitor's own DC (``CreateDCW`` on the device
    name), so dimming reaches all displays even when they sit on different
    graphics adapters (``GetDC(0)`` only reaches the primary adapter's LUT).
    """

    def __init__(self) -> None:
        # The gamma LUT starts at identity (100 %) — not Brightness.DEFAULT,
        # which would show 70 % on the slider while the screen is at full.
        self._current: int = 100

    def get(self) -> Brightness:
        return Brightness(self._current)

    def set(self, brightness: Brightness) -> None:
        try:
            dcs = _collect_monitor_dcs()
            if not dcs:
                logger.warning("No monitor DCs available for gamma ramp")
                return
            try:
                ramp = _build_ramp(brightness.value)
                ok = True
                for dc in dcs:
                    if not gdi32.SetDeviceGammaRamp(dc, ctypes.byref(ramp)):
                        ok = False
                if ok:
                    self._current = brightness.value
                else:
                    # The display driver rejected the ramp — common below its
                    # anti-blackout floor (e.g. Dell monitors reject < ~25 %).
                    # The screen stays at the last accepted level; report it
                    # informatively rather than warning on every slider tick.
                    logger.info(
                        "Gamma ramp rejected at %d %% (driver anti-blackout floor); "
                        "screen held at last accepted level", brightness.value
                    )
            finally:
                # DCs from CreateDCW must be freed with DeleteDC (not ReleaseDC).
                for dc in dcs:
                    gdi32.DeleteDC(dc)
        except Exception as exc:
            logger.warning("Gamma-ramp brightness set failed: %s", exc)


def _probe_sbc() -> BrightnessControl | None:
    """Return an sbc-backed control if sbc works on this display, else None."""
    try:
        import screen_brightness_control as sbc
        values = sbc.get_brightness()
        if values:
            return _SbcBrightnessControl(int(values[0]))
    except Exception as exc:
        logger.info("sbc brightness unavailable, falling back to gamma ramp: %s", exc)
    return None


class WindowsBrightnessControl(BrightnessControl):
    """Brightness control for Windows — picks the best backend at construction.

    Tries ``screen_brightness_control`` (real backlight) first; falls back to
    the Win32 gamma-ramp visual dimming when sbc raises or returns nothing.
    """

    def __init__(self) -> None:
        self._backend: BrightnessControl = _probe_sbc() or _GammaRampBrightnessControl()

    def get(self) -> Brightness:
        return self._backend.get()

    def set(self, brightness: Brightness) -> None:
        self._backend.set(brightness)
