"""Home Overlay menu composition — which entries appear given what is foreground.

Pure use-case (no Qt): decides the *structure* of the menu shown when BTN_MODE
opens the Home Overlay. Rendering (icons, translated labels, callbacks, overlay
lifecycle) stays in the Application wiring; this owns only the composition rule:

  - on the bare Desktop (idle) → just "return to desktop" + the system actions;
  - over a running app → app controls (return / close) + "return to desktop",
    no system actions, and dismissing returns to that app.
"""

from dataclasses import dataclass

from domain.catalog.target import Target
# Re-exported so existing importers keep using `domain.home_menu`.
from domain.menu.entry import CLOSE_APP, RETURN_TO_APP, RETURN_TO_DESKTOP, MenuEntry  # noqa: F401


@dataclass(frozen=True)
class HomeMenu:
    """The composed menu: ordered entries plus two structural flags the renderer
    needs (whether to append the system actions, and whether dismissing the
    overlay should return to the running app)."""

    entries: list[MenuEntry]
    include_system_actions: bool
    cancel_restores_app: bool


def compose_home_menu(foreground: Target | None) -> HomeMenu:
    """Compose the Home Overlay menu for the current foreground target."""
    if foreground is None:
        return HomeMenu(
            entries=[MenuEntry(RETURN_TO_DESKTOP)],
            include_system_actions=True,
            cancel_restores_app=False,
        )
    return HomeMenu(
        entries=[
            MenuEntry(RETURN_TO_APP, foreground.name),
            MenuEntry(CLOSE_APP, foreground.name),
            MenuEntry(RETURN_TO_DESKTOP),
        ],
        include_system_actions=False,
        cancel_restores_app=True,
    )
