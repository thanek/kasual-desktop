"""The screens Kasual Desktop can run on, and the ports that list, remember and
reach them."""

from dataclasses import dataclass
from typing import Protocol

from domain.shared.choice import SYSTEM_DECIDES as SYSTEM_DECIDES


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
    def aim_new_surfaces_at(self, display_id: str | None) -> None: ...
    def move_shown_surfaces_to(self, display_id: str | None) -> None: ...

    def moves_live(self) -> bool: ...


class PrimaryDisplay(Protocol):
    def lend_to_kasual_screen(self) -> None: ...
    def reclaim(self) -> None: ...
