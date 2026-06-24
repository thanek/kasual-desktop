"""Shared Win32 ``ShellExecuteEx`` plumbing for ``infrastructure.windows``.

``ctypes`` caches the ``shell32.ShellExecuteExW`` function pointer in a single
global object and validates every call against the registered ``argtypes``.
When two modules each define their own ``_SHELLEXECUTEINFO`` Structure those
classes are distinct (ctypes compares class identity, not field layout), so a
call from the module whose class wasn't the one registered trips::

    argument 1: TypeError: expected LP__SHELLEXECUTEINFO instance
    instead of pointer to _SHELLEXECUTEINFO

Defining the struct (and the ``SEE_MASK_NOCLOSEPROCESS`` flag) once here and
importing it in both ``app_manager`` and ``network`` keeps every caller using
the same class as the registered ``argtypes``.
"""

import ctypes
from ctypes import wintypes

SEE_MASK_NOCLOSEPROCESS = 0x00000040


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",         wintypes.DWORD),
        ("fMask",          wintypes.ULONG),
        ("hwnd",           wintypes.HWND),
        ("lpVerb",         wintypes.LPCWSTR),
        ("lpFile",         wintypes.LPCWSTR),
        ("lpParameters",   wintypes.LPCWSTR),
        ("lpDirectory",    wintypes.LPCWSTR),
        ("nShow",          wintypes.INT),
        ("hInstApp",       wintypes.HINSTANCE),
        ("lpIDList",       ctypes.c_void_p),
        ("lpClass",        wintypes.LPCWSTR),
        ("hkeyClass",      wintypes.HKEY),
        ("dwHotKey",       wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess",       wintypes.HANDLE),
    ]


# ``ctypes.windll`` exists only on Windows. Importing this module on Linux (which
# happens during pytest collection of Windows-only test modules that use the
# ``pytestmark`` skipif marker — that marker skips *execution*, not import) must
# not crash, so the shell32 binding and argtypes/restype registration are guarded
# and run only when the attribute is present.
if hasattr(ctypes, "windll"):
    _shell32 = ctypes.windll.shell32
    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFO)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
else:
    _shell32 = None