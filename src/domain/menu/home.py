"""Home Overlay menu composition — which sections/items appear given foreground.

Pure use-case (no Qt): composes the render-ready, sectioned content shown when
BTN_MODE opens the Home Overlay (§7.10) — localized labels, icons, and the
abstract action each item carries, grouped into the zones the bumpers step
between (Quick adjust ⇄ Actions ⇄ HUD). The overlay only renders these and reports
activation back; the controller dispatches the action.

  - on the bare Desktop (idle) → Quick adjust + the system-action grid;
  - over a running app → app controls (return / close), the HUD toggle when a
    HUD is configured, and "return to Home screen"; no system actions, and
    dismissing (B) returns to that app.
"""

from dataclasses import dataclass
from enum import StrEnum

from domain.catalog.target import Target
from domain.menu.entry import CLOSE_APP, POWER, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.item import MenuItem
from domain.shared.text import truncate
from domain.system.actions import (
    ACTIONS, BRIGHTNESS, HIDE_DESKTOP, NETWORK, NOTIFICATIONS, POWER_ACTIONS, VOLUME,
)
from domain.system.hud import HudControl, hud_menu_item
from domain.shared.i18n import translate


def _return_to_desktop_item() -> MenuItem:
    return MenuItem(translate("Kasual Desktop", "Return to Home screen"), RETURN_TO_DESKTOP, "fa5s.home")


# ── Home Overlay — sectioned model (§7.10) ──────────────────────────────────────
# The overlay groups its controls into zones the bumpers step between (Quick
# adjust ⇄ Actions ⇄ HUD); this composer returns those sections.


class SectionKind(StrEnum):
    """The Home Overlay zones (LB/RB step between them)."""

    HEADER  = "header"    # the status header's focusable Network / Notifications (§8)
    QUICK   = "quick"     # live sliders: volume, (brightness)
    ACTIONS = "actions"   # cards: power split-button, network, …, or app controls
    HUD     = "hud"       # the conditional in-game HUD toggle


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
    """A render-ready item for a system-action *key* (localized label + icon)."""
    action = ACTIONS[key]
    return MenuItem(translate("Kasual Desktop", action.label), key, action.icon)


def _power_card(power_default: str) -> MenuItem:
    """The Power split-button card, labelled by the current default action.

    Carries the abstract ``POWER`` action (not the concrete sleep/restart/shutdown
    key): the controller routes ``A`` to the default and ``Y`` to the dropdown
    (§7.10 / :class:`domain.system.power_menu.PowerMenu`). Label and icon mirror
    the default so the card reads e.g. "Sleep" with the moon glyph."""
    default = ACTIONS[power_default]
    return MenuItem(translate("Kasual Desktop", default.label), POWER, default.icon)


def power_dropdown_items() -> list[MenuItem]:
    """The Power split-button's expanded choices: Sleep / Restart / Shut Down.

    Each item carries its **concrete** power-action key (unlike the collapsed card,
    which carries the abstract ``POWER`` action), so the widget routes a pick
    straight through :meth:`domain.system.power_menu.PowerMenu.select`. Whichever
    key equals the current default is marked by the widget, not here."""
    return [_action_item(key) for key in POWER_ACTIONS]


def compose_home_sections(
    foreground: Target | None,
    hud: HudControl,
    *,
    brightness_controllable: bool,
    power_default: str,
    foreground_is_game: bool = False,
    include_status_actions: bool = True,
) -> HomeSections:
    """Compose the sectioned Home Overlay content for the current foreground.

    Quick adjust always offers volume, and brightness **only when the platform
    has a controllable backlight** (``brightness_controllable``, §7.3a). The
    Actions section is the global system grid on the bare Desktop — a Power
    split-button (labelled by *power_default*) plus network / notifications /
    minimize — or, over a running app, that app's controls (return / close /
    home) with the conditional HUD toggle in its own section (§7.10).

    ``include_status_actions`` drops Power / Network / Notifications from the grid
    when a navigable status header already carries them (§8 / Faza 5), so they
    aren't offered twice."""
    quick = [_action_item(VOLUME)]
    if brightness_controllable:
        quick.append(_action_item(BRIGHTNESS))

    if foreground is None:
        # "Return to Home screen" stays even on the Desktop context: when Kasual
        # is *minimized* it is the only way back (Minimize hides it, this restores
        # it — its dispatch is show_desktop with no foreground app). Harmless when
        # KD is already on screen (just re-raises).
        actions = []
        if include_status_actions:
            actions += [_power_card(power_default),
                        _action_item(NETWORK), _action_item(NOTIFICATIONS)]
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
