"""The screens Kasual Desktop can run on, and the ports that list, remember and
reach them."""

from dataclasses import dataclass
from typing import Protocol

SYSTEM_DECIDES = None


@dataclass(frozen=True)
class Display:
    id: str
    label: str
    connected: bool = True


class Displays(Protocol):
    def connected(self) -> list[Display]: ...


class DisplayPreference(Protocol):
    def preferred(self) -> str | None: ...
    def set_preferred(self, display_id: str | None) -> None: ...


class DisplayPlacement(Protocol):
    def aim_at(self, display_id: str | None) -> None:
        """Surfaces opened from now on go to *display_id*; shown ones stay put."""

    def move_to(self, display_id: str | None) -> None:
        """Shown surfaces go to *display_id* too — live, or through a relaunch
        where this desktop cannot move them."""

    def moves_live(self) -> bool: ...
