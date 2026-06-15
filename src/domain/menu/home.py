"""Home Overlay menu composition — which items appear given what is foreground.

Pure use-case (no Qt): composes the full, render-ready menu shown when BTN_MODE
opens the Home Overlay — localized labels, icons, and the abstract action each
item carries. The overlay only renders these and reports activation back; the
controller dispatches the action.

  - on the bare Desktop (idle) → "return to desktop" + the system actions;
  - over a running app → app controls (return / close), the HUD toggle when a
    HUD is configured, and "return to desktop"; no system actions, and
    dismissing (B) returns to that app.
"""

from dataclasses import dataclass

from domain.catalog.target import Target
from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.item import MenuItem
from domain.shared.text import truncate
from domain.system.action_view import system_action_items
from domain.system.hud import HudControl, hud_menu_item
from domain.shared.i18n import translate


@dataclass(frozen=True)
class HomeMenu:
    """The composed menu: ordered items plus what the B button does — restore a
    specific target, or None to just close the overlay."""

    items: list[MenuItem]
    cancel_restores: Target | None


def _return_to_desktop_item() -> MenuItem:
    return MenuItem(translate("Kasual Desktop", "Return to Desktop"), RETURN_TO_DESKTOP, "fa5s.home")


def compose_home_menu(foreground: Target | None, hud: HudControl) -> HomeMenu:
    """Compose the Home Overlay menu for the current foreground target.

    Over a running app the HUD toggle is offered too — but only when ``hud``
    reports a HUD is configured (see :func:`domain.system.hud.hud_menu_item`); on
    the bare Desktop it never appears."""
    if foreground is None:
        return HomeMenu(
            items=[_return_to_desktop_item(), *system_action_items()],
            cancel_restores=None,
        )
    name = truncate(foreground.name, 22)
    hud_item = hud_menu_item(hud)
    return HomeMenu(
        items=[
            MenuItem(
                translate("Kasual Desktop", "Return to {0}").format(name),
                RETURN_TO_APP, "fa5s.times", target=foreground,
            ),
            MenuItem(
                translate("Kasual Desktop", "Close {0}").format(name),
                CLOSE_APP, "fa5s.times-circle", target=foreground,
            ),
            *([hud_item] if hud_item is not None else []),
            _return_to_desktop_item(),
        ],
        cancel_restores=foreground,
    )
