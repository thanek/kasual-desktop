"""The audio-sink volume port (read/write as a percentage)."""

from typing import Protocol


class VolumeControl(Protocol):
    """Read/write the default audio sink volume as a percentage (0–100)."""

    def get(self) -> int: ...
    def set(self, percent: int) -> None: ...
