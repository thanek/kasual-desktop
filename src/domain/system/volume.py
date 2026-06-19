"""Volume value object — encapsulates the 0–100 range, step, and clamp rule."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from domain.system.bounded_value import BoundedValue


@dataclass(frozen=True)
class Volume(BoundedValue):
    STEP:    ClassVar[int] = 5
    DEFAULT: ClassVar[int] = 50
    # MIN inherited (0): muting to silence is fine, unlike screen brightness.


class VolumeControl(Protocol):
    """The audio-sink volume port."""

    def get(self) -> Volume: ...
    def set(self, volume: Volume) -> None: ...
