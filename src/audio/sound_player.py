"""
Playing short UI sounds via QAudioSink + Python wave.

WAV files are decoded at startup (init()) using the standard library
wave — no FFmpeg, no external tools. QAudioSink plays raw PCM
directly through Qt Audio.

Usage:
    import sound_player
    sound_player.init()          # once after QApplication
    sound_player.play("cursor")  # then anywhere
"""

import array
import logging
import wave
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSink

logger = logging.getLogger(__name__)

_SOUNDS_DIR = Path(__file__).parent.parent.parent / "sounds"
_SOUND_NAMES = ("cursor", "exit", "popup_open", "popup_close", "select", "start")

# name → (QAudioFormat, bytes)
_loaded: dict[str, tuple[QAudioFormat, bytes]] = {}

# Active sinks — we hold references until playback finishes
_active: list[tuple[QAudioSink, QBuffer]] = []


def _convert_24_to_16(data: bytes) -> bytes:
    """Converts raw 24-bit PCM (little-endian) to 16-bit."""
    out = array.array('h', [0] * (len(data) // 3))
    for i in range(len(out)):
        val24 = int.from_bytes(data[i * 3: i * 3 + 3], 'little', signed=True)
        out[i] = val24 >> 8
    return out.tobytes()


def _read_wav(path: Path) -> tuple[QAudioFormat, bytes] | None:
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


def init() -> None:
    """Decodes WAV files into memory. Call once after QApplication."""
    for name in _SOUND_NAMES:
        path = _SOUNDS_DIR / f"{name}.wav"
        if not path.exists():
            logger.warning("No sound file: %s", path)
            continue
        result = _read_wav(path)
        if result is not None:
            _loaded[name] = result
            logger.debug("Loaded sound: %s", name)


def play(name: str) -> bool:
    """Plays a previously loaded sound. Returns True if playback started."""
    entry = _loaded.get(name)
    if entry is None:
        logger.warning("Unknown sound or no init(): %s", name)
        return False

    # Remove finished sinks
    _active[:] = [
        (s, b) for s, b in _active
        if s.state() == QAudio.State.ActiveState
    ]

    fmt, data = entry
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)

    sink = QAudioSink(fmt)
    sink.start(buf)
    _active.append((sink, buf))
    return True
