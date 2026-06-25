"""Ask RTSS (via its shared memory) whether a PID is an actively-hooked 3D app.

RTSS publishes every application it hooks in the ``RTSSSharedMemoryV2`` file
mapping — one ``RTSS_SHARED_MEMORY_APP_ENTRY`` per app, in an array whose offset,
stride and length are given in the header (RTSS SDK ``RTSSSharedMemory.h``). An
entry whose **API-usage** flags are non-zero (``dwFlags & 0x0000FFFF`` → D3D8…12 /
OpenGL / Vulkan) is a process RTSS is actively rendering its OSD into — i.e. a
running 3D game. Plain hooked processes that aren't driving a 3D present loop
(RTSS lists them with only the architecture bit, e.g. the desktop shell) have a
zero API-usage field and are excluded.

This is the signal the Windows in-game HUD uses to decide whether the toggle
applies, instead of inferring game-ness from the process tree / launcher names —
RTSS already knows exactly which foreground app it is drawing on.

The ``_scan_for_3d_pid`` core is a pure function over a ``read_u32(offset)``
reader, so the field parsing is unit-tested without RTSS; ``RtssAppProbe`` is the
thin ctypes wrapper that maps the shared memory and feeds that reader.
"""

from __future__ import annotations

import ctypes
import logging
import struct
from ctypes import wintypes
from typing import Callable

logger = logging.getLogger(__name__)

_MAP_NAME = "RTSSSharedMemoryV2"
_FILE_MAP_READ = 0x0004

# 'RTSS' DWORD signature, as read little-endian from the mapping (bytes "SSTR").
_SIGNATURE = 0x52545353
_APPFLAG_API_USAGE_MASK = 0x0000FFFF

# Header field offsets (RTSS_SHARED_MEMORY).
_OFF_SIGNATURE = 0
_OFF_APP_ENTRY_SIZE = 8     # stride of one RTSS_SHARED_MEMORY_APP_ENTRY
_OFF_APP_ARR_OFFSET = 12    # offset of the app-entry array
_OFF_APP_ARR_SIZE = 16      # number of app entries
# Per-entry offsets: dwProcessID, then szName[MAX_PATH=260], then dwFlags.
_ENTRY_OFF_PROCESS_ID = 0
_ENTRY_OFF_FLAGS = 264

_MAX_ENTRIES = 4096  # sanity cap, guards against a garbage array size


def _scan_for_3d_pid(read_u32: Callable[[int], int], pid: int) -> bool:
    """True if *pid* is an app entry with a non-zero API-usage flag (a 3D game).

    Pure over ``read_u32(offset)``; returns False on a bad signature or an
    implausible array description."""
    if read_u32(_OFF_SIGNATURE) != _SIGNATURE:
        return False
    entry_size = read_u32(_OFF_APP_ENTRY_SIZE)
    arr_offset = read_u32(_OFF_APP_ARR_OFFSET)
    arr_size = read_u32(_OFF_APP_ARR_SIZE)
    if entry_size == 0 or not (0 < arr_size <= _MAX_ENTRIES):
        return False
    for i in range(arr_size):
        base = arr_offset + i * entry_size
        if read_u32(base + _ENTRY_OFF_PROCESS_ID) == pid:
            flags = read_u32(base + _ENTRY_OFF_FLAGS)
            return (flags & _APPFLAG_API_USAGE_MASK) != 0
    return False


class RtssAppProbe:
    """Queries RTSS's shared memory for actively-hooked 3D applications."""

    def __init__(self) -> None:
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "windll") else None
        if self._k32 is not None:
            self._k32.OpenFileMappingW.restype = wintypes.HANDLE
            self._k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
            self._k32.MapViewOfFile.restype = ctypes.c_void_p
            self._k32.MapViewOfFile.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t
            ]
            self._k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
            self._k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def is_3d_app(self, pid: int) -> bool:
        """True if RTSS is actively hooking *pid* as a 3D app (a running game).

        Opens the mapping fresh each call so a started/stopped RTSS or game is
        always reflected; any failure (RTSS down, no access) reads as False."""
        if pid is None or pid <= 0 or self._k32 is None:
            return False
        handle = self._k32.OpenFileMappingW(_FILE_MAP_READ, False, _MAP_NAME)
        if not handle:
            return False  # RTSS not running
        view = None
        try:
            view = self._k32.MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, 0)
            if not view:
                return False
            base = int(view)
            read_u32 = lambda off: struct.unpack_from("<I", ctypes.string_at(base + off, 4))[0]
            return _scan_for_3d_pid(read_u32, pid)
        except OSError as exc:
            logger.warning("RTSS shared-memory read failed: %s", exc)
            return False
        finally:
            if view:
                self._k32.UnmapViewOfFile(ctypes.c_void_p(view))
            self._k32.CloseHandle(handle)
