"""Volume value object — encapsulates the 0–100 range, step, and clamp rule."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol


@dataclass(frozen=True)
class Volume:
    STEP: ClassVar[int] = 5
    DEFAULT: ClassVar[int] = 50

    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, 'value', max(0, min(100, self.value)))

    def adjusted(self, delta: int) -> Volume:
        return Volume(self.value + delta)

"""The audio-sink volume port."""
class VolumeControl(Protocol):
    def get(self) -> Volume: ...
    def set(self, volume: Volume) -> None: ...
