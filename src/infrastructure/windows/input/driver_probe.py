"""Probe for ViGEmBus and HidHide kernel drivers at startup.

Returns a frozen :class:`DriverCapabilities` that the gamepad watcher uses to
decide between exclusive mode (both drivers present → virtual pad + hidden
physical device) and cooperative fallback (either missing → today's behaviour).

The probe is intentionally lightweight: it attempts a real connect/disconnect
cycle for ViGEmBus (the only definitive way to check the bus driver is live)
and a registry read for HidHide. Both are wrapped in broad exception handlers
so a broken driver or missing DLL silently falls back to cooperative mode
rather than crashing the app.

Cached once per process by :class:`WindowsGamepadWatcher`; the result does not
change without a reboot or driver reinstall.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DriverCapabilities:
    """Which kernel drivers are installed and operational."""

    vigembus: bool   # ViGEmBus driver installed & a client can connect
    hidhide: bool    # HidHide driver installed & registry is readable

    @property
    def exclusive(self) -> bool:
        """True only when BOTH drivers are present (all-or-nothing, D4)."""
        return self.vigembus and self.hidhide


def probe_drivers() -> DriverCapabilities:
    """Check for ViGEmBus and HidHide; return capabilities.

    Called once at startup. Each probe is independent — a failure in one does
    not affect the other. All exceptions are caught and logged at DEBUG so the
    log stays clean on machines without the drivers (the common case).
    """
    vigem = _probe_vigembus()
    hidhide = _probe_hidhide()
    caps = DriverCapabilities(vigembus=vigem, hidhide=hidhide)
    if caps.exclusive:
        logger.info("Driver probe: ViGEmBus + HidHide present (exclusive mode available)")
    else:
        logger.info(
            "Driver probe: ViGEmBus=%s HidHide=%s (cooperative fallback)",
            vigem, hidhide,
        )
    return caps


def _probe_vigembus() -> bool:
    """Attempt a connect/disconnect cycle with ViGEmClient.dll.

    The DLL might be present but the bus driver absent — ``vigem_connect``
    returns ``VIGEM_ERROR_BUS_NOT_FOUND`` in that case. A successful
    connect+disconnect is the only definitive proof the bus is live.
    """
    try:
        from infrastructure.windows.input.vigembus_writer import VigemWriter

        writer = VigemWriter()
        writer.connect()
        writer.disconnect()
        return True
    except Exception as exc:
        logger.debug("ViGEmBus probe failed: %s", exc)
        return False


def _probe_hidhide() -> bool:
    """Check that the HidHide registry hive is readable.

    HidHide stores its configuration under ``HKLM\\SOFTWARE\\Nefarius\\HidHide``.
    If the base key exists, the driver is installed. We don't need write access
    for the probe — the actual whitelist/blacklist writes happen later and are
    allowed to fail (which would force a cooperative fallback at runtime).
    """
    try:
        from infrastructure.windows.input.hidhide import HidHideClient

        client = HidHideClient()
        return client.ping()
    except Exception as exc:
        logger.debug("HidHide probe failed: %s", exc)
        return False
