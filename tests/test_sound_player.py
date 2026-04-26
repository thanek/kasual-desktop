"""Tests for pure helper functions in audio/sound_player.py."""

import struct

import pytest

from audio.sound_player import _convert_24_to_16


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
