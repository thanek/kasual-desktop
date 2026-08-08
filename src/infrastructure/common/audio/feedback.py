"""The `Feedback` port's sound adapter — short UI cues via QAudioSink + wave.

WAV files decode into memory once at init() (stdlib `wave`, no FFmpeg) and
play as raw PCM. State lives on the instance, so one shared instance is
created at the composition root and injected wherever cues are emitted.
"""

import array
import logging
import wave
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QTimer
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSink

from domain.shared.feedback import Cue, Feedback
from infrastructure.common.bundled import bundled_dir

logger = logging.getLogger(__name__)

_SOUNDS_DIR = bundled_dir("sounds")
_SOUND_NAMES = tuple(c.value for c in Cue)


def _convert_24_to_16(data: bytes) -> bytes:
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
            sample_width = wf.getsampwidth()
            data         = wf.readframes(wf.getnframes())

            # QAudioSink does not support 24-bit.
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
    """Implements the `Feedback` port over Qt Audio."""

    def __init__(self) -> None:
        self._loaded: dict[str, tuple[QAudioFormat, bytes]] = {}
        # Held until playback finishes, or QAudioSink would be GC'd mid-sound.
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

    def play(self, cue: Cue) -> None:
        """Plays a previously loaded cue (no-op if unknown or not yet init()ed)."""
        entry = self._loaded.get(cue)
        if entry is None:
            logger.warning("Unknown sound or no init(): %s", cue)
            return

        fmt, data = entry
        buf = QBuffer()
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)

        sink = QAudioSink(fmt)
        # Refills run on the GUI thread, so a frame longer than the buffer
        # punches silence into the cue.
        sink.setBufferSize(len(data))
        sink.stateChanged.connect(
            lambda state, played=sink: self._on_state_changed(played, state))
        sink.start(buf)
        self._active.append((sink, buf))

    def _on_state_changed(self, sink: QAudioSink, state: QAudio.State) -> None:
        if state is QAudio.State.IdleState:
            self._release(sink)

    def _release(self, sink: QAudioSink) -> None:
        sink.stop()
        # Dropping the last reference inside the sink's own signal would delete
        # it mid-emission.
        QTimer.singleShot(0, lambda: self._forget(sink))

    def _forget(self, sink: QAudioSink) -> None:
        self._active[:] = [(s, b) for s, b in self._active if s is not sink]
