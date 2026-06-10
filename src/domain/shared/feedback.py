"""The audio-cue feedback port — cross-cutting, used across subdomains."""

from typing import Protocol


class Feedback(Protocol):
    """Audio cue feedback for application-driven events ('select', …). Keeps the
    use-case layer from importing the sound backend directly."""

    def play(self, cue: str) -> None: ...
