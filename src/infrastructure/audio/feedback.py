"""Adapter for the `Feedback` port — plays audio cues via the sound backend.

Co-located with `sound_player` (its dependency); lets the application layer
trigger cues ('select', …) without importing the audio module directly.
"""

from infrastructure.audio import sound_player
from domain.shared.feedback import Feedback


class SoundFeedback(Feedback):
    """Implements `ports.Feedback` over `audio.sound_player`."""

    def play(self, cue: str) -> None:
        sound_player.play(cue)
