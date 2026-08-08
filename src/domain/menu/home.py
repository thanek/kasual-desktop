"""Composes the sectioned Home Overlay content for the current foreground."""

from dataclasses import dataclass
from enum import StrEnum

from domain.catalog.target import Target
from domain.menu.entry import CLOSE_APP, POWER, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.item import MenuItem
from domain.shared.text import truncate
from domain.system.actions import (
    ACTIONS, BRIGHTNESS, GAMEPAD_ACCESS, HIDE_DESKTOP, NETWORK, NOTIFICATIONS,
    POWER_ACTIONS, VOLUME,
)
from domain.system.hud import HudControl, hud_menu_item
from domain.shared.i18n import translate


def _return_to_desktop_item() -> MenuItem:
    """Offered on the Home screen too: when Kasual Desktop is minimized this is
    the only way back, and it merely re-raises when it is already on screen."""
    return MenuItem(translate("Kasual Desktop", "Return to Home screen"), RETURN_TO_DESKTOP, "fa5s.home")


class SectionKind(StrEnum):
    """The Home Overlay zones the bumpers step between."""

    HEADER  = "header"
    QUICK   = "quick"
    ACTIONS = "actions"
    HUD     = "hud"


@dataclass(frozen=True)
class HomeSection:
    kind:  SectionKind
    items: list[MenuItem]


@dataclass(frozen=True)
class HomeSections:
    """The Home Overlay content: ordered sections + what B restores."""

    sections:        list[HomeSection]
    cancel_restores: Target | None


def _action_item(key: str) -> MenuItem:
    action = ACTIONS[key]
    return MenuItem(translate("Kasual Desktop", action.label), key, action.icon)


def _power_card(power_default: str) -> MenuItem:
    """Carries the abstract POWER action, not the concrete key, so A runs the
    default and Y opens the dropdown; label and icon mirror the default."""
    default = ACTIONS[power_default]
    return MenuItem(translate("Kasual Desktop", default.label), POWER, default.icon)


def power_dropdown_items() -> list[MenuItem]:
    """Each item carries its concrete power-action key, so a pick routes straight
    through, unlike the collapsed card's abstract POWER."""
    return [_action_item(key) for key in POWER_ACTIONS]


def compose_home_sections(
    foreground: Target | None,
    hud: HudControl,
    *,
    brightness_controllable: bool,
    power_default: str,
    foreground_is_game: bool = False,
    include_status_actions: bool = True,
    gamepad_access_checkable: bool = False,
) -> HomeSections:
    """Brightness is offered only when the backlight is controllable;
    ``include_status_actions`` drops Power / Network / Notifications from the grid
    when a status header already carries them, so they aren't offered twice;
    ``gamepad_access_checkable`` is false where the pad does not come from evdev
    and there is nothing to grant."""
    quick = [_action_item(VOLUME)]
    if brightness_controllable:
        quick.append(_action_item(BRIGHTNESS))

    if foreground is None:
        actions = []
        if include_status_actions:
            actions += [_power_card(power_default),
                        _action_item(NETWORK), _action_item(NOTIFICATIONS)]
        if gamepad_access_checkable:
            actions.append(_action_item(GAMEPAD_ACCESS))
        actions += [_action_item(HIDE_DESKTOP), _return_to_desktop_item()]
        return HomeSections(
            sections=[HomeSection(SectionKind.QUICK, quick),
                      HomeSection(SectionKind.ACTIONS, actions)],
            cancel_restores=None,
        )

    name = truncate(foreground.name, 22)
    actions = [
        MenuItem(translate("Kasual Desktop", "Return to {0}").format(name),
                 RETURN_TO_APP, "fa5s.times", target=foreground),
        MenuItem(translate("Kasual Desktop", "Close {0}").format(name),
                 CLOSE_APP, "fa5s.times-circle", target=foreground),
        _return_to_desktop_item(),
    ]
    sections = [HomeSection(SectionKind.QUICK, quick),
                HomeSection(SectionKind.ACTIONS, actions)]
    hud_item = hud_menu_item(hud, foreground_is_game)
    if hud_item is not None:
        sections.append(HomeSection(SectionKind.HUD, [hud_item]))
    return HomeSections(sections, cancel_restores=foreground)
