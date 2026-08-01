"""Platform-dispatch for gamepad input in bundled apps.

On Linux, Kasual grabs the physical gamepad exclusively and exposes a virtual
``kasual-vpad`` device via UInput. Bundled apps read from that virtual device
and emit keyboard events back through UInput — the Qt widget picks them up as
ordinary key presses.

On Windows, the gamepad is cooperative (every app sees XInput/SDL events
natively), so apps read the controller directly via pygame and emit keyboard
events through Win32 ``SendInput``. Kasual itself stays out of the way while a
bundled app has the foreground (the controller isn't grabbed).

This module provides the cross-platform seam: a ``press(key)`` function and a
``Key`` enum with the subset of Linux ``ecodes.KEY_*`` the apps use. On Linux
these are re-exported from ``evdev``; on Windows ``Key`` maps to Win32 virtual-
key codes and ``press`` calls ``SendInput``.
"""

import sys

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    # Win32 SendInput structures and binding.
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    # Full Win32 INPUT union — all three members must be present so ctypes
    # computes the same sizeof(INPUT) as the real Win32 API expects. Omitting
    # MOUSEINPUT (the largest) makes SendInput fail with ERROR_INVALID_PARAMETER
    # because cbSize doesn't match.
    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", _MOUSEINPUT),
            ("ki", _KEYBDINPUT),
            ("hi", _HARDWAREINPUT),
        ]

    class _INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", _INPUT_UNION),
        ]

    _user32 = ctypes.windll.user32
    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT

    # Map the Linux ecodes.KEY_* used by the apps to Win32 virtual-key codes.
    # https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
    _VK = {
        "KEY_ENTER":  0x0D,
        "KEY_ESC":    0x1B,
        "KEY_LEFT":   0x25,
        "KEY_UP":     0x26,
        "KEY_RIGHT":  0x27,
        "KEY_DOWN":   0x28,
        "KEY_H":      0x48,
        "KEY_S":      0x53,
        "KEY_R":      0x52,
        "KEY_MINUS":  0xBD,
        "KEY_EQUAL":  0xBB,
        "KEY_PAGEUP": 0x21,
        "KEY_PAGEDOWN": 0x22,
    }

    class Key:
        """Subset of Linux ecodes.KEY_* the apps use, mapped to Win32 VK codes."""
        KEY_ENTER = "KEY_ENTER"
        KEY_ESC = "KEY_ESC"
        KEY_LEFT = "KEY_LEFT"
        KEY_UP = "KEY_UP"
        KEY_RIGHT = "KEY_RIGHT"
        KEY_DOWN = "KEY_DOWN"
        KEY_H = "KEY_H"
        KEY_S = "KEY_S"
        KEY_R = "KEY_R"
        KEY_MINUS = "KEY_MINUS"
        KEY_EQUAL = "KEY_EQUAL"
        KEY_PAGEUP = "KEY_PAGEUP"
        KEY_PAGEDOWN = "KEY_PAGEDOWN"

    def press(key_name: str) -> None:
        """Send a key press+release via Win32 SendInput."""
        vk = _VK.get(key_name)
        if vk is None:
            return
        inp = _INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = 0
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

else:
    from evdev import UInput
    from evdev import ecodes as e

    _ui = UInput()

    class Key:
        """Re-export of the Linux ecodes.KEY_* constants the apps use."""
        KEY_ENTER = e.KEY_ENTER
        KEY_ESC = e.KEY_ESC
        KEY_LEFT = e.KEY_LEFT
        KEY_UP = e.KEY_UP
        KEY_RIGHT = e.KEY_RIGHT
        KEY_DOWN = e.KEY_DOWN
        KEY_H = e.KEY_H
        KEY_S = e.KEY_S
        KEY_R = e.KEY_R
        KEY_MINUS = e.KEY_MINUS
        KEY_EQUAL = e.KEY_EQUAL
        KEY_PAGEUP = e.KEY_PAGEUP
        KEY_PAGEDOWN = e.KEY_PAGEDOWN

    def press(key: int) -> None:
        """Send a key press+release via evdev UInput."""
        _ui.write(e.EV_KEY, key, 1)
        _ui.write(e.EV_KEY, key, 0)
        _ui.syn()
