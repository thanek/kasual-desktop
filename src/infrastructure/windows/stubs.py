"""Placeholder Windows adapters for capabilities not yet implemented.

These satisfy the domain ports the shared Desktop is wired against so the desktop
runs end-to-end on Windows while the real volume/brightness/network/power/pinning
backends are still pending (see windows_plan.md, Iteracja 2). Each is a no-op or
logs a TODO; none changes system state.
"""

import logging

logger = logging.getLogger(__name__)


class StubPowerControl:
    def suspend(self) -> None:
        logger.info("TODO: Sleep/Suspend not implemented on Windows")

    def reboot(self) -> None:
        logger.info("TODO: Restart not implemented on Windows")

    def poweroff(self) -> None:
        logger.info("TODO: Shutdown not implemented on Windows")


class StubVolumeControl:
    def get(self) -> float:
        return 0.5

    def set(self, value: float) -> None:
        pass


class StubBrightnessControl:
    def get(self) -> float:
        return 0.75

    def set(self, value: float) -> None:
        pass


class StubNetworkControl:
    def connect(self, network_id: str) -> None:
        pass

    def disconnect(self) -> None:
        pass


class StubTileColorStore:
    def get_color(self, idx: int) -> str | None:
        return None

    def set_color(self, idx: int, color: str) -> None:
        pass


class StubAppPinning:
    def pin(self, window) -> None:
        pass

    def unpin(self, idx: int) -> None:
        pass
