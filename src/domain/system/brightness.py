"""Brightness value object — encapsulates the range, step, and clamp rule.

Mirrors :class:`domain.system.volume.Volume`, but floors at a non-zero minimum:
unlike audio, a screen brightness of 0 is a black, effectively unrecoverable
screen, so the domain refuses to dim below ``MIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from domain.system.bounded_value import BoundedValue


@dataclass(frozen=True)
class Brightness(BoundedValue):
    MIN:     ClassVar[int] = 5
    STEP:    ClassVar[int] = 10
    DEFAULT: ClassVar[int] = 70


class BrightnessControl(Protocol):
    """The display-backlight brightness port.

    Deliberately minimal so it can be backed by whatever the host desktop exposes —
    a generic CLI (brightnessctl), sysfs, or a DE-specific D-Bus service (KDE
    PowerManagement, GNOME settings daemon). The concrete adapter is chosen at the
    composition root; see
    :func:`infrastructure.linux.display.brightness.select_brightness_control`."""

    def get(self) -> Brightness: ...
    def set(self, brightness: Brightness) -> None: ...
