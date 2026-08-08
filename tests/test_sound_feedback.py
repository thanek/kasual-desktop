"""Tests for audio/feedback.py (SoundFeedback backend)."""

import struct

import pytest

from PyQt6.QtMultimedia import QAudio

from domain.shared.feedback import Cue
from infrastructure.common.audio import feedback
from infrastructure.common.audio.feedback import _convert_24_to_16


def _encode_24(val: int) -> bytes:
    return val.to_bytes(3, byteorder='little', signed=True)


def _decode_16(data: bytes) -> int:
    return struct.unpack_from('<h', data)[0]


class TestConvert24To16:
    def test_zero(self):
        assert _convert_24_to_16(_encode_24(0)) == b'\x00\x00'

    def test_positive_max(self):
        # 8388607 >> 8 == 32767
        out = _convert_24_to_16(_encode_24(8_388_607))
        assert _decode_16(out) == 8_388_607 >> 8

    def test_negative_min(self):
        # -8388608 >> 8 == -32768
        out = _convert_24_to_16(_encode_24(-8_388_608))
        assert _decode_16(out) == -8_388_608 >> 8

    def test_output_is_half_the_length(self):
        raw = _encode_24(0) * 8   # 8 samples → 24 bytes
        assert len(_convert_24_to_16(raw)) == 16  # 8 samples → 16 bytes

    def test_multiple_samples(self):
        samples = [0, 8_388_607, -8_388_608, 1024 * 256]
        raw = b"".join(_encode_24(s) for s in samples)
        out = _convert_24_to_16(raw)
        assert len(out) == len(samples) * 2
        for i, s in enumerate(samples):
            got = _decode_16(out[i * 2:])
            assert got == s >> 8

    def test_empty_input(self):
        assert _convert_24_to_16(b"") == b""


class FakeSignal:
    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)

    def emit(self, state):
        for handler in self.handlers:
            handler(state)


class FakeSink:
    instances: list['FakeSink'] = []

    def __init__(self, _fmt):
        self.buffer_size = None
        self.started_bytes = None
        self.stopped = False
        self.stateChanged = FakeSignal()
        FakeSink.instances.append(self)

    def setBufferSize(self, size):
        self.buffer_size = size

    def start(self, device):
        self.started_bytes = device.size()

    def stop(self):
        self.stopped = True


class TestPlay:
    @pytest.fixture(autouse=True)
    def silence_sounds(self):
        # Overrides conftest's autouse patch of play(), the method under test.
        yield

    @pytest.fixture
    def sound(self, monkeypatch):
        FakeSink.instances = []
        monkeypatch.setattr(feedback, 'QAudioSink', FakeSink)
        played = feedback.SoundFeedback()
        played.init()
        return played

    def test_the_sink_is_sized_to_hold_the_whole_cue(self, sound):
        sound.play(Cue.CURSOR)

        sink, = FakeSink.instances
        assert sink.started_bytes > 0
        assert sink.buffer_size == sink.started_bytes

    def test_a_cue_that_played_out_releases_its_stream(self, sound):
        sound.play(Cue.CURSOR)
        sink, = FakeSink.instances

        sink.stateChanged.emit(QAudio.State.IdleState)

        assert sink.stopped

    def test_a_cue_still_playing_keeps_its_stream(self, sound):
        sound.play(Cue.CURSOR)
        sink, = FakeSink.instances

        sink.stateChanged.emit(QAudio.State.ActiveState)

        assert not sink.stopped
