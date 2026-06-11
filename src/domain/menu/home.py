"""Home Overlay menu composition — which items appear given what is foreground.

Pure use-case (no Qt): composes the full, render-ready menu shown when BTN_MODE
opens the Home Overlay — localized labels, icons, and the abstract action each
item carries. The overlay only renders these and reports activation back; the
controller dispatches the action.

  - on the bare Desktop (idle) → "return to desktop" + the system actions;
  - over a running app → app controls (return / close) + "return to desktop",
    no system actions, and dismissing (B) returns to that app.
"""

from dataclasses import dataclass

from domain.catalog.target import Target
from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP
from domain.menu.item import MenuItem
from domain.shared.text import truncate
from domain.system.action_view import system_action_items
from support.i18n import translate


@dataclass(frozen=True)
class HomeMenu:
    """The composed menu: ordered items plus what the B button does — restore a
    specific target, or None to just close the overlay."""

    items: list[MenuItem]
    cancel_restores: Target | None


def _return_to_desktop_item() -> MenuItem:
    return MenuItem(translate("Kasual", "Return to Desktop"), RETURN_TO_DESKTOP, "fa5s.home")


def compose_home_menu(foreground: Target | None) -> HomeMenu:
    """Compose the Home Overlay menu for the current foreground target."""
    if foreground is None:
        return HomeMenu(
            items=[_return_to_desktop_item(), *system_action_items()],
            cancel_restores=None,
        )
    name = truncate(foreground.name, 22)
    return HomeMenu(
        items=[
            MenuItem(
                translate("Kasual", "Return to {0}").format(name),
                RETURN_TO_APP, "fa5s.times", target=foreground,
            ),
            MenuItem(
                translate("Kasual", "Close {0}").format(name),
                CLOSE_APP, "fa5s.times-circle", target=foreground,
            ),
            _return_to_desktop_item(),
        ],
        cancel_restores=foreground,
    )
