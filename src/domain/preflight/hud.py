"""The in-game HUD reaching games Kasual Desktop did not start itself.

Kasual Desktop can arm the HUD only for what it launches (see
:mod:`infrastructure.linux.hud.mangohud`), so a game started by a launcher that
was already running gets none, and no toggle over it either. This card says so;
the ways out are in :mod:`domain.preflight.hud_recipes`, and who is asked, how
often, is the composition root's to decide.
"""

from __future__ import annotations

from typing import Protocol

from domain.setup.plan import Assessment, Check, StatusLine, Subject
from domain.setup.ports import Requirement
from domain.shared.i18n import translate

NO_SESSION_HUD = "hud-not-in-session"


class HudEnvironment(Protocol):
    """The session's own environment, as the HUD is gated on it."""

    def carried_by_session(self) -> bool:
        """Whether everything started in this session — launchers included, and
        so the games they start — comes up with the HUD loaded."""
        ...


class HudSetupMemory(Protocol):
    """Remembers that the card has been put in front of the user, so it is not
    put there again."""

    def was_ever_shown(self) -> bool: ...
    def mark_shown(self) -> None: ...


class HudInSession(Requirement):
    def __init__(self, environment: HudEnvironment) -> None:
        self._environment = environment

    def subject(self) -> Subject:
        return Subject(
            title=translate(
                "Kasual Desktop", "The performance HUD reaches only some games"),
            unsupported=translate(
                "Kasual Desktop",
                "Kasual Desktop has no recipe for reaching the rest of this "
                "system's games. The ones it starts itself still get the HUD; the "
                "ones a running launcher starts do not.",
            ),
        )

    def assess(self) -> Assessment:
        if self._environment.carried_by_session():
            return Assessment((self._reaching(),))
        return Assessment((self._not_reaching(),), (NO_SESSION_HUD,))

    def satisfied(self, check: Check) -> bool:
        return False

    @staticmethod
    def _reaching() -> StatusLine:
        return StatusLine(
            translate("Kasual Desktop", "Every game in this session can show the HUD"),
            met=True,
        )

    @staticmethod
    def _not_reaching() -> StatusLine:
        return StatusLine(
            translate("Kasual Desktop", "Only games Kasual Desktop starts get the HUD"),
            met=False,
            detail=translate(
                "Kasual Desktop",
                "MangoHud draws over a game only when that game was started with "
                "MANGOHUD=1 in its environment. Kasual Desktop passes it to what it "
                "launches — but a launcher that is already running takes the request "
                "over and starts the game itself, from its own environment, and the "
                "HUD never loads. Over such a game the Home Menu offers no HUD "
                "toggle, because there would be nothing on screen for it to switch.",
            ),
        )
