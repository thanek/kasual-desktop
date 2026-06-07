"""PowerControl adapter over ``systemctl``."""

import logging
import subprocess

logger = logging.getLogger(__name__)


class SystemdPowerControl:
    """Implements the PowerControl port by shelling out to ``systemctl``."""

    def suspend(self) -> None:
        self._run("suspend")

    def reboot(self) -> None:
        self._run("reboot")

    def poweroff(self) -> None:
        self._run("poweroff")

    @staticmethod
    def _run(verb: str) -> None:
        try:
            subprocess.Popen(["systemctl", verb])
        except Exception as exc:
            logger.error("systemctl %s failed: %s", verb, exc)
