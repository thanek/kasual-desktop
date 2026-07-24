"""The `Feedback` port's sound adapter — short UI cues via QSoundEffect.

QSoundEffect is Qt's path for exactly this shape of sound: a small PCM WAV played
over and over, each effect holding one stream for its lifetime. The obvious
alternative — a QAudioSink per playback — does not survive the workload. The cues
run for whole seconds, so sweeping the cursor along the tile bar leaves dozens of
them overlapping, and Qt's PulseAudio backend aborts the process on its own
assertions; worse, that backend never reports a drained sink as idle, so nothing
reclaims them and they simply pile up. Reusing one sink per cue fixes the pile-up
but still crashes on teardown.

One effect per cue is built by init() and re-triggered on play. WAVs must be 8- or
16-bit PCM — what QSoundEffect decodes, and what the bundled cues are.
"""

import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect

from domain.shared.feedback import Cue, Feedback
from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_SOUNDS_DIR = bundled_dir("sounds")


class SoundFeedback(Feedback):
    """Implements the `Feedback` port over Qt's sound-effect player."""

    def __init__(self) -> None:
        self._effects: dict[str, QSoundEffect] = {}

    def init(self) -> None:
        """Builds one player per cue. Call once after QApplication."""
        for cue in Cue:
            path = _SOUNDS_DIR / f"{cue.value}.wav"
            if not path.exists():
                logger.warning("No sound file: %s", path)
                continue
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(path)))
            self._effects[cue] = effect
            logger.debug("Loaded sound: %s", cue.value)

    def play(self, cue: Cue) -> None:
        """Plays a previously loaded cue (no-op if unknown or not yet init()ed)."""
        effect = self._effects.get(cue)
        if effect is None:
            logger.warning("Unknown sound or no init(): %s", cue)
            return
        # Restart rather than layer a second copy over the first, which is what a
        # cue should do as the cursor sweeps from tile to tile.
        effect.stop()
        effect.play()
