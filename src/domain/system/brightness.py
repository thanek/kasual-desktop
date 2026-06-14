"""Brightness value object — encapsulates the range, step, and clamp rule.

Mirrors :class:`domain.system.volume.Volume`, but floors at a non-zero minimum:
unlike audio, a screen brightness of 0 is a black, effectively unrecoverable
screen, so the domain refuses to dim below ``MIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from typing import Protocol


@dataclass(frozen=True)
class Brightness:
    STEP: ClassVar[int] = 10
    DEFAULT: ClassVar[int] = 70
    MIN: ClassVar[int] = 5

    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, 'value', max(self.MIN, min(100, self.value)))

    def adjusted(self, delta: int) -> Brightness:
        return Brightness(self.value + delta)


"""The display-backlight brightness port.

Deliberately minimal so it can be backed by whatever the host desktop exposes —
a generic CLI (brightnessctl), sysfs, or a DE-specific D-Bus service (KDE
PowerManagement, GNOME settings daemon). The concrete adapter is chosen at the
composition root; see
:func:`infrastructure.system.brightness.select_brightness_control`."""
class BrightnessControl(Protocol):
    def get(self) -> Brightness: ...
    def set(self, brightness: Brightness) -> None: ...
