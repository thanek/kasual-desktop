"""The Desktop capabilities that system actions drive."""

from typing import Protocol


class DesktopShell(Protocol):
    """The Desktop capabilities that system actions drive."""

    def open_volume_overlay(self) -> None: ...
    def pause(self) -> None: ...
