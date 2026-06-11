"""Presentation for the system actions — how each one looks and reads.

Maps the action keys from `domain.system.actions` to their icon, colour and
localized label, plus the wording of the confirmation question (for the ones the
catalog marks as needing one). This is the "HOW it looks/reads"; the "WHAT it is
/ does" lives in the action catalog next door.

It lives in the domain because it is the vocabulary of the actions, not an
adapter — its only outward need is translation, which it gets through the
`support.i18n` port rather than from Qt directly.

`make_action_confirm` bridges the two: the `ActionRunner` calls back with an
action *key*; this resolves the localized question for that key and hands it to
the actual confirm-dialog opener.
"""

from collections.abc import Callable
from dataclasses import dataclass

from domain.system.actions import HIDE_DESKTOP, RESTART, SHUTDOWN, SLEEP, VOLUME
from support.i18n import translate


@dataclass(frozen=True)
class ActionView:
    label:            str          # source string; re-translated at render time
    icon:             str          # qtawesome glyph name
    color:            str
    confirm_question: str | None   # source string; None for immediate actions


# The `translate(...)` calls below run at import time — before the composition
# root installs a backend — so they return the source string unchanged and act
# purely as extraction markers (pylupdate6 harvests them). The actual
# localization happens when consumers re-translate the label at render time
# (see home_overlay / make_action_confirm); don't drop that step.
PRESENTATION: dict[str, ActionView] = {
    VOLUME: ActionView(
        translate("Kasual", "Volume"),
        "fa5s.volume-up", "#3b4252", None,
    ),
    SLEEP: ActionView(
        translate("Kasual", "Sleep"),
        "fa5s.moon", "#4c566a",
        translate("Kasual", "Are you sure you want to sleep?"),
    ),
    RESTART: ActionView(
        translate("Kasual", "Restart"),
        "fa5s.redo-alt", "#5e81ac",
        translate("Kasual", "Are you sure you want to restart?"),
    ),
    SHUTDOWN: ActionView(
        translate("Kasual", "Shut Down"),
        "fa5s.power-off", "#bf616a",
        translate("Kasual", "Are you sure you want to shut down?"),
    ),
    HIDE_DESKTOP: ActionView(
        translate("Kasual", "Minimize Desktop"),
        "fa5s.window-minimize", "#d580ff", None,
    ),
}


def make_action_confirm(
    show_confirm: Callable[[str, Callable[[], None]], None],
) -> Callable[[str, Callable[[], None]], None]:
    """Adapt a (question_text, on_confirmed) opener into the (action_key,
    on_confirmed) callback the ActionRunner expects, resolving the localized
    question for the key."""
    def confirm(action_key: str, on_confirmed: Callable[[], None]) -> None:
        question = translate("Kasual", PRESENTATION[action_key].confirm_question)
        show_confirm(question, on_confirmed)
    return confirm
