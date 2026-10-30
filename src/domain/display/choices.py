"""The screens offered to the user to pick from, as every picker presents them."""

from typing import Protocol

from domain.display.display import SYSTEM_DECIDES, Display
from domain.shared.choice import Choice, connection_aware_label
from domain.shared.i18n import translate

ScreenChoice = Choice[str | None]


class ScreenOptions(Protocol):
    def options(self) -> list[Display]: ...
    def chosen(self) -> str | None: ...


def screen_choices(displays: ScreenOptions) -> list[ScreenChoice]:
    chosen = displays.chosen()
    leave_it_to_the_system = ScreenChoice(
        translate("Kasual Desktop", "Chosen by the system"),
        SYSTEM_DECIDES, pickable=True, chosen=chosen == SYSTEM_DECIDES,
    )
    return [leave_it_to_the_system,
            *(_choice_of(display, chosen) for display in displays.options())]


def _choice_of(display: Display, chosen: str | None) -> ScreenChoice:
    return ScreenChoice(
        connection_aware_label(display.label, display.connected), display.id,
        pickable=display.connected, chosen=display.id == chosen,
    )
