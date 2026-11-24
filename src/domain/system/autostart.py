"""Whether the system starts Kasual Desktop on its own."""

from typing import Protocol

from domain.shared.i18n import translate


class Autostart(Protocol):
    def is_enabled(self) -> bool: ...
    def set_enabled(self, enabled: bool) -> None: ...


def autostart_label() -> str:
    return translate("Kasual Desktop", "Start Kasual Desktop at system startup")


class AutostartChoice:
    def __init__(self, autostart: Autostart) -> None:
        self._autostart = autostart
        self._wanted = autostart.is_enabled()

    @property
    def is_on(self) -> bool:
        return self._wanted

    def toggle(self) -> None:
        self._wanted = not self._wanted

    def apply(self) -> None:
        if self._wanted != self._autostart.is_enabled():
            self._autostart.set_enabled(self._wanted)
