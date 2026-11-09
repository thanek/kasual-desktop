"""The screens offered to the user to pick from, as every picker presents them."""

from typing import Protocol

from domain.display.display import Display
from domain.shared.choice import Choice, system_first_choices

ScreenChoice = Choice[str | None]


class ScreenOptions(Protocol):
    def options(self) -> list[Display]: ...
    def chosen(self) -> str | None: ...


def screen_choices(displays: ScreenOptions) -> list[ScreenChoice]:
    return system_first_choices(displays.options(), displays.chosen())
