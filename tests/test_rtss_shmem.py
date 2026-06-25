"""Tests for the RTSS shared-memory app scan (infrastructure.windows.hud.rtss_shmem).

The ctypes mapping can't be exercised off Windows, so the field parsing is split
into the pure ``_scan_for_3d_pid`` over a ``read_u32(offset)`` reader. These build
a synthetic shared-memory image and assert the discriminator: an app entry counts
as a game only when its API-usage flags (low word of dwFlags) are non-zero — the
plain architecture-only entries RTSS keeps for non-3D processes do not.
"""

import struct

from infrastructure.windows.hud.rtss_shmem import (
    _APPFLAG_API_USAGE_MASK,
    _ENTRY_OFF_FLAGS,
    _OFF_APP_ARR_OFFSET,
    _OFF_APP_ARR_SIZE,
    _OFF_APP_ENTRY_SIZE,
    _SIGNATURE,
    _scan_for_3d_pid,
)

_ARR_OFFSET = 64
_ENTRY_SIZE = _ENTRY_OFF_FLAGS + 8  # room for dwProcessID … dwFlags


def _image(entries, *, signature=_SIGNATURE, arr_size=None):
    """Build a shared-memory image (bytearray) with the given (pid, flags) entries."""
    size = _ARR_OFFSET + _ENTRY_SIZE * (len(entries) + 1)
    buf = bytearray(size)
    struct.pack_into("<I", buf, 0, signature)
    struct.pack_into("<I", buf, _OFF_APP_ENTRY_SIZE, _ENTRY_SIZE)
    struct.pack_into("<I", buf, _OFF_APP_ARR_OFFSET, _ARR_OFFSET)
    struct.pack_into("<I", buf, _OFF_APP_ARR_SIZE, arr_size if arr_size is not None else len(entries))
    for i, (pid, flags) in enumerate(entries):
        base = _ARR_OFFSET + i * _ENTRY_SIZE
        struct.pack_into("<I", buf, base, pid)
        struct.pack_into("<I", buf, base + _ENTRY_OFF_FLAGS, flags)
    return buf


def _reader(buf):
    return lambda off: struct.unpack_from("<I", buf, off)[0]


_ARCH_X64 = 0x00010000          # architecture bit only — not a 3D app
_D3D11 = _ARCH_X64 | 0x0007     # API-usage low word set — a running game
_VULKAN = _ARCH_X64 | 0x000A


class TestScan:
    def test_pid_with_api_flag_is_a_game(self):
        buf = _image([(5488, _ARCH_X64), (15392, _D3D11)])
        assert _scan_for_3d_pid(_reader(buf), 15392) is True

    def test_vulkan_api_flag_is_a_game(self):
        buf = _image([(15392, _VULKAN)])
        assert _scan_for_3d_pid(_reader(buf), 15392) is True

    def test_pid_with_only_arch_flag_is_not_a_game(self):
        # RTSS lists non-3D processes (the shell, helpers) with the arch bit only.
        buf = _image([(5488, _ARCH_X64)])
        assert _scan_for_3d_pid(_reader(buf), 5488) is False

    def test_pid_absent_from_table(self):
        buf = _image([(5488, _ARCH_X64), (15392, _D3D11)])
        assert _scan_for_3d_pid(_reader(buf), 99999) is False

    def test_bad_signature_reads_as_no_game(self):
        buf = _image([(15392, _D3D11)], signature=0xDEADDEAD)
        assert _scan_for_3d_pid(_reader(buf), 15392) is False

    def test_zero_array_size_reads_as_no_game(self):
        buf = _image([(15392, _D3D11)], arr_size=0)
        assert _scan_for_3d_pid(_reader(buf), 15392) is False

    def test_implausible_array_size_reads_as_no_game(self):
        buf = _image([(15392, _D3D11)], arr_size=10_000_000)
        assert _scan_for_3d_pid(_reader(buf), 15392) is False

    def test_mask_constant_is_low_word(self):
        assert _APPFLAG_API_USAGE_MASK == 0x0000FFFF