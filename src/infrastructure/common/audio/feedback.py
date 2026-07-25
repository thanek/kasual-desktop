"""The `Feedback` port's sound adapter — short UI cues via QSoundEffect.

One player per sounding, never rewound before its WAV has run out: cutting a player
short damages it until the cues fall silent altogether, and this backend never
reports a drained player as idle, so the timing is kept here. A press with every
player of its cue still sounding goes unheard. See the README for the underlying
Qt 6.4 bug, which no arrangement here cures.
"""

import logging
import time
import wave

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaDevices, QSoundEffect

from domain.shared.feedback import Cue, Feedback
from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_SOUNDS_DIR = bundled_dir("sounds")
_VOICES = 8            # players per cue: how many may be sounding at once
_UNKNOWN_LENGTH = 3.0  # held for this long when the WAV will not give its length
_TAIL_S = 0.5          # what the sound takes to leave the audio server after that


class SoundFeedback(Feedback):
    """Implements the `Feedback` port over Qt's sound-effect player."""

    def __init__(self) -> None:
        self._voices: dict[str, list[QSoundEffect]] = {}
        self._free_at: dict[str, list[float]] = {}   # when each player finishes
        self._length: dict[str, float] = {}
        self._devices: QMediaDevices | None = None

    def init(self) -> None:
        """Builds the players for every cue. Call once after QApplication."""
        # Kept alive for the signal below, which no instance emits once collected.
        self._devices = QMediaDevices()
        self._devices.audioOutputsChanged.connect(self._follow_default_output)
        for cue in Cue:
            path = _SOUNDS_DIR / f"{cue.value}.wav"
            if not path.exists():
                logger.warning("No sound file: %s", path)
                continue
            source = QUrl.fromLocalFile(str(path))
            voices = []
            for _ in range(_VOICES):
                effect = QSoundEffect()
                effect.setSource(source)
                voices.append(effect)
            self._voices[cue] = voices
            self._free_at[cue] = [0.0] * _VOICES
            self._length[cue] = _length_of(path)
            logger.debug("Loaded sound: %s (%.2fs)", cue.value, self._length[cue])
        self._follow_default_output()

    def _follow_default_output(self) -> None:
        output = QMediaDevices.defaultAudioOutput()
        if output.isNull():
            logger.warning("No audio output — cues will play into nothing")
            return
        for effect in self._all_effects():
            effect.setAudioDevice(output)
        logger.info("Sound cues play on %s", output.description())

    def _all_effects(self) -> list[QSoundEffect]:
        return [effect for voices in self._voices.values() for effect in voices]

    def play(self, cue: Cue) -> None:
        """Plays a previously loaded cue (no-op if unknown or not yet init()ed)."""
        voices = self._voices.get(cue)
        if not voices:
            logger.warning("Unknown sound or no init(): %s", cue)
            return
        now = time.monotonic()
        free_at = self._free_at[cue]
        index = min(range(len(voices)), key=lambda i: free_at[i])
        if free_at[index] > now:
            return              # every player of this cue is still sounding
        free_at[index] = now + self._length[cue] + _TAIL_S
        # A player left marked as playing ignores play() until it is stopped.
        voices[index].stop()
        voices[index].play()


def _length_of(path: Path) -> float:
    """How long the cue sounds for."""
    try:
        with wave.open(str(path)) as cue:
            return cue.getnframes() / cue.getframerate()
    except (OSError, wave.Error) as exc:
        logger.warning("Could not read the length of %s: %s", path, exc)
        return _UNKNOWN_LENGTH
