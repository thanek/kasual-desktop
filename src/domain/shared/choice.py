"""One entry of a pick-one list, as every picker presents it."""

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from domain.shared.i18n import translate

T = TypeVar("T")

SYSTEM_DECIDES = None


@dataclass(frozen=True)
class Choice(Generic[T]):
    label: str
    value: T
    pickable: bool
    chosen: bool


class Option(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def connected(self) -> bool: ...


def connection_aware_label(label: str, connected: bool) -> str:
    if connected:
        return label
    return translate("Kasual Desktop", "{0} (not connected)").format(label)


def system_first_choices(options: list[Option], chosen: str | None) -> list[Choice[str | None]]:
    leave_it_to_the_system = Choice(
        translate("Kasual Desktop", "Chosen by the system"),
        SYSTEM_DECIDES, pickable=True, chosen=chosen == SYSTEM_DECIDES,
    )
    return [leave_it_to_the_system, *(_choice_of(option, chosen) for option in options)]


def remembered_but_absent(connected: list[Option], preferred: str | None) -> bool:
    return preferred is not SYSTEM_DECIDES and all(option.id != preferred for option in connected)


def _choice_of(option: Option, chosen: str | None) -> Choice[str | None]:
    return Choice(
        connection_aware_label(option.label, option.connected), option.id,
        pickable=option.connected, chosen=option.id == chosen,
    )
