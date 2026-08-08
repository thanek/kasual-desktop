"""Tests for the Wayland wire format — encoders, framing and the argument reader."""

import struct

import pytest

from infrastructure.linux.wayland import wire


def _header(payload_len: int, opcode: int) -> int:
    return ((wire.HEADER_SIZE + payload_len) << 16) | opcode


class TestEncoding:
    def test_request_header_carries_size_and_opcode(self):
        raw = wire.encode_request(7, 3, wire.uint(42))
        sender, word, value = struct.unpack("=III", raw)
        assert (sender, word, value) == (7, _header(4, 3), 42)

    def test_request_without_arguments_is_header_only(self):
        assert wire.encode_request(1, 0) == struct.pack("=II", 1, _header(0, 0))

    def test_string_is_length_with_nul_then_padding(self):
        raw = wire.string("ab")
        assert raw == struct.pack("=I", 3) + b"ab\0\0"

    def test_string_already_aligned_gets_no_extra_word(self):
        assert wire.string("abc") == struct.pack("=I", 4) + b"abc\0"

    def test_empty_string_is_a_single_nul(self):
        assert wire.string("") == struct.pack("=I", 1) + b"\0\0\0\0"

    def test_array_is_length_then_padded_bytes(self):
        assert wire.array(b"\x01\x02") == struct.pack("=I", 2) + b"\x01\x02\0\0"

    def test_fixed_is_signed_24_8(self):
        assert wire.fixed(-1.5) == struct.pack("=i", -384)

    def test_bind_new_id_carries_interface_and_version(self):
        raw = wire.new_id_bind("wl_seat", 4, 9)
        assert raw == wire.string("wl_seat") + wire.uint(4) + wire.uint(9)


class TestFraming:
    def test_splits_consecutive_messages(self):
        stream = (wire.encode_request(1, 0, wire.uint(1))
                  + wire.encode_request(2, 5, wire.string("hi")))
        messages, rest = wire.iter_messages(stream)
        assert rest == b""
        assert [(m.sender, m.opcode) for m in messages] == [(1, 0), (2, 5)]

    def test_keeps_a_partial_message_for_the_next_read(self):
        stream = wire.encode_request(1, 0, wire.uint(1))
        messages, rest = wire.iter_messages(stream[:-2])
        assert messages == []
        assert rest == stream[:-2]

    def test_completes_a_message_split_across_reads(self):
        stream = wire.encode_request(3, 1, wire.string("split"))
        first, rest = wire.iter_messages(stream[:6])
        second, tail = wire.iter_messages(rest + stream[6:])
        assert first == [] and tail == b""
        assert second[0].sender == 3

    def test_truncated_header_is_left_alone(self):
        messages, rest = wire.iter_messages(b"\x01\x02\x03")
        assert messages == [] and rest == b"\x01\x02\x03"

    def test_impossible_size_stops_the_scan(self):
        broken = struct.pack("=II", 1, (4 << 16) | 0)
        messages, rest = wire.iter_messages(broken)
        assert messages == [] and rest == broken


class TestReader:
    def test_reads_arguments_in_order(self):
        payload = (wire.uint(1) + wire.string("kasual") + wire.uint(3)
                   + wire.int32(-7) + wire.fixed(2.5))
        reader = wire.Reader(payload)
        assert reader.uint() == 1
        assert reader.string() == "kasual"
        assert reader.uint() == 3
        assert reader.int32() == -7
        assert reader.fixed() == 2.5

    def test_uint_array_reads_the_words_it_holds(self):
        payload = wire.array(struct.pack("=III", 0, 2, 3))
        assert wire.Reader(payload).uint_array() == [0, 2, 3]

    def test_empty_array_reads_as_no_words(self):
        assert wire.Reader(wire.array(b"")).uint_array() == []

    def test_reading_past_the_end_is_an_error(self):
        with pytest.raises(ValueError):
            wire.Reader(wire.uint(1)).string()

    def test_string_longer_than_the_payload_is_an_error(self):
        with pytest.raises(ValueError):
            wire.Reader(struct.pack("=I", 64) + b"short").string()
