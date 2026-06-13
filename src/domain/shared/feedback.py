"""The audio-cue feedback port — cross-cutting, used across subdomains."""

from typing import Protocol

from enum import StrEnum

class Cue(StrEnum):
    CURSOR      = "cursor"
    EXIT        = "exit"
    POPUP_OPEN  = "popup_open"
    POPUP_CLOSE = "popup_close"
    SELECT      = "select"
    START       = "start"


class Feedback(Protocol):
    """Audio cue feedback for application-driven events. Keeps the use-case
    layer from importing the sound backend directly."""

    def play(self, cue: Cue) -> None: ...
