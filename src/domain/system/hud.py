"""The in-game performance HUD (MangoHud) — port plus the toggle's logic: whether
it is offered, how it reads, and which way a press flips it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from domain.catalog.app import App
from domain.menu.entry import TOGGLE_HUD
from domain.menu.item import MenuItem
from domain.shared.i18n import translate


class HudControl(Protocol):
    """Port onto the performance HUD's availability and on/off state.
    ``is_available`` gates the whole feature."""

    def is_available(self) -> bool: ...
    def is_enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...

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
    """The HUD toggle, or ``None`` when a press would have nothing to switch. The
    label always names what a press will do."""
    if not hud.is_available():
        return None
    if not foreground_is_game:
        return None
    if not hud.is_attached(foreground_pid):
        return None
    if hud.is_enabled():
        return MenuItem(translate("Kasual Desktop", "Disable HUD"), TOGGLE_HUD, "fa5s.eye-slash")
    return MenuItem(translate("Kasual Desktop", "Enable HUD"), TOGGLE_HUD, "fa5s.eye")


def toggle_hud(hud: HudControl) -> None:
    """Flip the HUD: turn it off when on, on when off."""
    if hud.is_enabled():
        hud.disable()
    else:
        hud.enable()
