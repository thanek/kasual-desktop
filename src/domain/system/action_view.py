"""Rendering the system actions — turning the catalog into menu items / a confirm.

The action catalog (identity + effect + presentation) is the single source of
truth in :mod:`domain.system.actions`. This module renders from it: the home-menu
items and the confirm-dialog callback. It lives in the domain because it is the
vocabulary of the actions, not an adapter — its only outward need is translation,
through the `domain.shared.i18n` port.

`make_action_confirm` bridges the runner and the view: the `ActionRunner` calls
back with an action *key*; this resolves the localized question for that key and
hands it to the actual confirm-dialog opener.
"""

from collections.abc import Callable
from dataclasses import dataclass

from domain.menu.entry import POWER
from domain.menu.item import MenuItem
from domain.system.actions import ACTIONS, HIDE_DESKTOP, NETWORK, NOTIFICATIONS
from domain.shared.i18n import translate


@dataclass(frozen=True)
class TopBarItem:
    """One top-bar button: the key it dispatches on plus its glyph and colour.

    ``action`` is a system-action key the controller runs, or the abstract
    ``POWER`` for the split-button (which the controller routes to the persisted
    default action)."""

    action: str
    icon:   str
    color:  str


def topbar_items(power_default: str) -> list[TopBarItem]:
    """The top-bar buttons, in order: a single **Power** button (glyph mirrors the
    persisted *power_default*) plus Network, Notifications, Minimize.

    Volume/Brightness and the Sleep/Restart/Shut Down trio are deliberately absent
    — volume/brightness live in the Home Overlay's Quick adjust, and the trio
    collapses into the one Power split-button (§7.10)."""
    default = ACTIONS[power_default]
    keep = (NETWORK, NOTIFICATIONS, HIDE_DESKTOP)
    return [
        TopBarItem(POWER, default.icon, default.color),
        *(TopBarItem(key, ACTIONS[key].icon, ACTIONS[key].color) for key in keep),
    ]


def system_action_items() -> list[MenuItem]:
    """The system actions (volume, sleep, …) as menu items, in catalog order.

    Each item's `action` is the action key the ActionRunner dispatches on; the
    label is localized here (the catalog strings are extraction-marker sources)."""
    return [
        MenuItem(
            label=translate("Kasual Desktop", action.label),
            action=key,
            icon=action.icon,
        )
        for key, action in ACTIONS.items()
    ]


def make_action_confirm(
    show_confirm: Callable[[str, Callable[[], None]], None],
) -> Callable[[str, Callable[[], None]], None]:
    """Adapt a (question_text, on_confirmed) opener into the (action_key,
    on_confirmed) callback the ActionRunner expects, resolving the localized
    question for the key."""
    def confirm(action_key: str, on_confirmed: Callable[[], None]) -> None:
        question = translate("Kasual Desktop", ACTIONS[action_key].confirm_question)
        show_confirm(question, on_confirmed)
    return confirm
