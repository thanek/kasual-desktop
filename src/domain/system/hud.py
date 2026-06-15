"""The in-game performance HUD (MangoHud) — port plus the toggle's rough logic.

This owns only the "WHAT": whether the HUD feature is offered at all, how the
toggle reads given the current state, and which way a press flips it. The "HOW"
— where the on/off state lives and how it is changed (a MangoHud config file) —
sits behind the :class:`HudControl` port, implemented in
``infrastructure.mangohud``. Keeping the file mechanics out is what lets this
stay a pure, Qt-free, filesystem-free domain citizen.

The toggle is offered only over a running app (the Home Overlay's "game mode"
branch) and only where a HUD is actually configured; see
:func:`domain.menu.home.compose_home_menu`.
"""

from __future__ import annotations

from typing import Protocol

from domain.menu.entry import TOGGLE_HUD
from domain.menu.item import MenuItem
from domain.shared.i18n import translate


class HudControl(Protocol):
    """Port onto the performance HUD's availability and on/off state.

    ``is_available`` gates the whole feature: where the host has no HUD
    configured at all, the toggle is never offered. The enable/disable mechanics
    (and what "enabled" means) live entirely in the infrastructure adapter."""

    def is_available(self) -> bool: ...
    def is_enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...


def hud_menu_item(hud: HudControl) -> MenuItem | None:
    """The HUD toggle as a menu item, or ``None`` when the feature is unavailable.

    Reads as "Disable HUD" while the HUD is on and "Enable HUD" while it is off,
    so the label always names what a press will do."""
    if not hud.is_available():
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
