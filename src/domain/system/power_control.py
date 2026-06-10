"""The system-power port (suspend / reboot / power off)."""

from typing import Protocol


class PowerControl(Protocol):
    """System power actions (suspend / reboot / power off)."""

    def suspend(self) -> None: ...
    def reboot(self) -> None: ...
    def poweroff(self) -> None: ...
