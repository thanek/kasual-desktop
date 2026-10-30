"""One entry of a pick-one list, as every picker presents it."""

from dataclasses import dataclass
from typing import Generic, TypeVar

from domain.shared.i18n import translate

T = TypeVar("T")


@dataclass(frozen=True)
class Choice(Generic[T]):
    label: str
    value: T
    pickable: bool
    chosen: bool


def connection_aware_label(label: str, connected: bool) -> str:
    if connected:
        return label
    return translate("Kasual Desktop", "{0} (not connected)").format(label)
