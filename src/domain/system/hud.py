"""The in-game performance HUD and its level slider."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol, Self

from domain.catalog.app import App
from domain.menu.entry import HUD_LEVEL
from domain.menu.item import MenuItem
from domain.shared.i18n import translate

HUD_OFF = 0


@dataclass(frozen=True)
class HudLevel:
    value:         int
    most_detailed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", max(HUD_OFF, min(self.most_detailed, self.value)))

    @property
    def is_off(self) -> bool:
        return self.value == HUD_OFF

    @property
    def label(self) -> str:
        if self.is_off:
            return translate("Kasual Desktop", "Off")
        return str(self.value)

    def adjusted(self, delta: int) -> Self:
        return replace(self, value=self.value + delta)

    def at(self, value: int) -> Self:
        return replace(self, value=value)


class HudControl(Protocol):
    def is_available(self) -> bool: ...
    def level(self) -> HudLevel: ...
    def set_level(self, level: HudLevel) -> None: ...

    def launch_env(self) -> Mapping[str, str]:
        """Environment a game must be started with for the HUD to attach to it;
        empty where the HUD hooks running games by itself (RTSS)."""
        return {}

    def is_attached(self, pid: int | None) -> bool:
        """Whether the HUD is loaded into *pid* — ``launch_env`` reaches only what
        Kasual Desktop starts itself. True where the HUD hooks games by itself."""
        return True


def hud_launch_env(hud: HudControl, app: App) -> Mapping[str, str]:
    """The HUD's :meth:`launch_env` for *app*, or nothing — only games get it, or
    any app rendering through the same graphics API would get the HUD too."""
    if not app.is_game or not hud.is_available():
        return {}
    return hud.launch_env()


def hud_menu_item(hud: HudControl, foreground_is_game: bool,
                  foreground_pid: int | None) -> MenuItem | None:
    if not hud.is_available():
        return None
    if not foreground_is_game:
        return None
    if not hud.is_attached(foreground_pid):
        return None
    return MenuItem(translate("Kasual Desktop", "Performance overlay"), HUD_LEVEL,
                    "fa5s.tachometer-alt")
