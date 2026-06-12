"""The `Feedback` port's sound adapter — short UI cues via QAudioSink + wave.

`SoundFeedback` is the *only* place the audio backend lives: WAV files are
decoded into memory at startup (`init()`, once after QApplication, using the
standard-library `wave` module — no FFmpeg) and played as raw PCM through Qt
Audio. The application layer triggers cues ('select', …) through the `Feedback`
port and never touches this backend directly.

State (decoded sounds, live sinks) lives on the instance, so a single shared
SoundFeedback is created at the composition root and injected wherever cues are
emitted.
"""

import array
import logging
import wave
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSink

from domain.shared.feedback import Feedback

logger = logging.getLogger(__name__)

# sounds/ lives at the repo root; this file sits at src/infrastructure/audio/,
# so the root is four levels up (parents[3]).
_SOUNDS_DIR = Path(__file__).resolve().parents[3] / "sounds"
_SOUND_NAMES = ("cursor", "exit", "popup_open", "popup_close", "select", "start")


def _convert_24_to_16(data: bytes) -> bytes:
    """Converts raw 24-bit PCM (little-endian) to 16-bit."""
    out = array.array('h', [0] * (len(data) // 3))
    for i in range(len(out)):
        val24 = int.from_bytes(data[i * 3: i * 3 + 3], 'little', signed=True)
        out[i] = val24 >> 8
    return out.tobytes()


def _read_wav(path: Path) -> 'tuple[QAudioFormat, bytes] | None':
    try:
        with wave.open(str(path)) as wf:
            n_channels   = wf.getnchannels()
            sample_rate  = wf.getframerate()
            sample_width = wf.getsampwidth()  # bytes per sample
            data         = wf.readframes(wf.getnframes())

            # 24-bit PCM → convert to 16-bit (QAudioSink does not support 24-bit)
            if sample_width == 3:
                data         = _convert_24_to_16(data)
                sample_width = 2

            fmt = QAudioFormat()
            fmt.setSampleRate(sample_rate)
            fmt.setChannelCount(n_channels)
            if sample_width == 1:
                fmt.setSampleFormat(QAudioFormat.SampleFormat.UInt8)
            elif sample_width == 2:
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            elif sample_width == 4:
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int32)
            else:
                logger.warning("Unsupported sample format (%d B): %s", sample_width, path)
                return None

            return fmt, data
    except Exception:
        logger.exception("Error reading WAV: %s", path)
        return None


class SoundFeedback(Feedback):
    """Implements the `Feedback` port over Qt Audio. One shared, init()-ed
    instance is injected wherever cues are played."""

    def __init__(self) -> None:
        # name → (QAudioFormat, bytes); live sinks held until playback finishes.
        self._loaded: dict[str, tuple[QAudioFormat, bytes]] = {}
        self._active: list[tuple[QAudioSink, QBuffer]] = []

    def init(self) -> None:
        """Decodes WAV files into memory. Call once after QApplication."""
        for name in _SOUND_NAMES:
            path = _SOUNDS_DIR / f"{name}.wav"
            if not path.exists():
                logger.warning("No sound file: %s", path)
                continue
            result = _read_wav(path)
            if result is not None:
                self._loaded[name] = result
                logger.debug("Loaded sound: %s", name)

    def play(self, cue: str) -> None:
        """Plays a previously loaded cue (no-op if unknown or not yet init()ed)."""
        entry = self._loaded.get(cue)
        if entry is None:
            logger.warning("Unknown sound or no init(): %s", cue)
            return

        # Drop finished sinks before starting a new one.
        self._active[:] = [
            (s, b) for s, b in self._active
            if s.state() == QAudio.State.ActiveState
        ]

        fmt, data = entry
        buf = QBuffer()
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)

        sink = QAudioSink(fmt)
        sink.start(buf)
        self._active.append((sink, buf))
