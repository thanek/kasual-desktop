"""Presentation for the system actions — how each one looks and reads.

Maps the action keys from `application.system_actions` to their icon, colour and
localized label, plus the wording of the confirmation question (for the ones the
catalog marks as needing one). This is the "HOW it looks/reads"; the "WHAT it is
/ does" lives in the application catalog.

`make_action_confirm` bridges the two: the application `ActionRunner` calls back
with an action *key*; this resolves the localized question for that key and hands
it to the actual confirm-dialog opener.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from application.system_actions import (
    HIDE_DESKTOP, RESTART, SHUTDOWN, SLEEP, VOLUME,
)


@dataclass(frozen=True)
class ActionView:
    label:            str          # QT_TRANSLATE_NOOP — translated at render time
    icon:             str          # qtawesome glyph name
    color:            str
    confirm_question: str | None   # QT_TRANSLATE_NOOP; None for immediate actions


PRESENTATION: dict[str, ActionView] = {
    VOLUME: ActionView(
        QT_TRANSLATE_NOOP("Kasual", "Volume"),
        "fa5s.volume-up", "#3b4252", None,
    ),
    SLEEP: ActionView(
        QT_TRANSLATE_NOOP("Kasual", "Sleep"),
        "fa5s.moon", "#4c566a",
        QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to sleep?"),
    ),
    RESTART: ActionView(
        QT_TRANSLATE_NOOP("Kasual", "Restart"),
        "fa5s.redo-alt", "#5e81ac",
        QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to restart?"),
    ),
    SHUTDOWN: ActionView(
        QT_TRANSLATE_NOOP("Kasual", "Shut Down"),
        "fa5s.power-off", "#bf616a",
        QT_TRANSLATE_NOOP("Kasual", "Are you sure you want to shut down?"),
    ),
    HIDE_DESKTOP: ActionView(
        QT_TRANSLATE_NOOP("Kasual", "Minimize Desktop"),
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
        question = QCoreApplication.translate(
            "Kasual", PRESENTATION[action_key].confirm_question
        )
        show_confirm(question, on_confirmed)
    return confirm
