"""Ports — the abstract capabilities the app depends on, implemented by infra
adapters (system/power.py, system/volume.py) and by the Desktop view.

Structural (Protocol) typing: an adapter conforms by shape, it need not inherit.
This is the boundary that keeps the application/registry layer free of pactl,
systemctl and Desktop internals.
"""

from typing import Protocol


class PowerControl(Protocol):
    """System power actions (suspend / reboot / power off)."""

    def suspend(self) -> None: ...
    def reboot(self) -> None: ...
    def poweroff(self) -> None: ...


class VolumeControl(Protocol):
    """Read/write the default audio sink volume as a percentage (0–100)."""

    def get(self) -> int: ...
    def set(self, percent: int) -> None: ...


class DesktopShell(Protocol):
    """The Desktop capabilities that system actions drive."""

    def open_volume_overlay(self) -> None: ...
    def pause(self) -> None: ...
