"""Windows power control — sleep / restart / shut down (the PowerControl port).

Sleep uses ``SetSuspendState`` (powrprof); restart/shutdown shell out to the
system ``shutdown`` tool, which carries the required privilege itself (so we
avoid the AdjustTokenPrivileges dance ExitWindowsEx would need).
"""

import ctypes
import logging
import subprocess

from domain.system.power_control import PowerControl

logger = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000


class WindowsPowerControl(PowerControl):
    """Implements the PowerControl port via Win32."""

    def suspend(self) -> None:
        logger.info("Suspending (sleep)")
        try:
            # SetSuspendState(bHibernate=FALSE, bForce=FALSE, bWakeupEventsDisabled=FALSE)
            ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
        except Exception as exc:
            logger.error("Sleep failed: %s", exc)

    def reboot(self) -> None:
        logger.info("Rebooting")
        self._shutdown("/r")

    def poweroff(self) -> None:
        logger.info("Shutting down")
        self._shutdown("/s")

    @staticmethod
    def _shutdown(flag: str) -> None:
        try:
            subprocess.run(["shutdown", flag, "/t", "0"],
                           creationflags=_CREATE_NO_WINDOW, check=False)
        except Exception as exc:
            logger.error("shutdown %s failed: %s", flag, exc)
