"""
Odtwarzanie krótkich dźwięków UI przez QAudioSink + Python wave.

Pliki WAV są dekodowane przy starcie (init()) przez standardową bibliotekę
wave — bez FFmpeg, bez zewnętrznych narzędzi. QAudioSink gra surowe PCM
bezpośrednio przez Qt Audio.

Użycie:
    import sound_player
    sound_player.init()          # raz po QApplication
    sound_player.play("cursor")  # potem w dowolnym miejscu
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

# Aktywne sinki — trzymamy referencje do czasu zakończenia odtwarzania
_active: list[tuple[QAudioSink, QBuffer]] = []


def _convert_24_to_16(data: bytes) -> bytes:
    """Konwertuje surowe 24-bit PCM (little-endian) na 16-bit."""
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

            # 24-bit PCM → konwertuj do 16-bit (QAudioSink nie obsługuje 24-bit)
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
                logger.warning("Nieobsługiwana głębia bitowa (%d B): %s", sample_width, path)
                return None

            return fmt, data
    except Exception:
        logger.exception("Błąd odczytu WAV: %s", path)
        return None


def init() -> None:
    """Dekoduje pliki WAV do pamięci. Wywołać raz po QApplication."""
    for name in _SOUND_NAMES:
        path = _SOUNDS_DIR / f"{name}.wav"
        if not path.exists():
            logger.warning("Brak pliku dźwiękowego: %s", path)
            continue
        result = _read_wav(path)
        if result is not None:
            _loaded[name] = result
            logger.debug("Załadowano dźwięk: %s", name)


def play(name: str) -> None:
    """Odtwarza wcześniej załadowany dźwięk."""
    entry = _loaded.get(name)
    if entry is None:
        logger.warning("Nieznany dźwięk lub brak init(): %s", name)
        return

    # Usuń zakończone sinki
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
