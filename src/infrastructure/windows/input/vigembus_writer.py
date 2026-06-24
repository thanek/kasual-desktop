"""Virtual Xbox360 gamepad writer via ViGEmBus (ctypes → ViGEmClient.dll).

Mirrors the Linux evdev ``UInput`` model: the Windows gamepad watcher forwards
physical gamepad events to a virtual ``kasual-vpad`` Xbox360 controller so that
foreground apps (Steam, games, bundled apps) see gamepad input without direct
access to the physical device (which is hidden by HidHide).

The writer maintains an internal ``XUSB_REPORT`` (the XInput state struct) and
sends the full report on every write — ViGEmBus accepts the complete state each
call, so there is no explicit SYN/commit step (``syn()`` is a no-op, kept for
API parity with evdev).

The ``vigembus`` Python binding is not published on PyPI, so this module talks
to ``ViGEmClient.dll`` directly through ctypes (the documented fallback in the
plan, section 13). The DLL ships with the ViGEmClient SDK; it is searched for
in the usual system locations and the application directory.

Testability: all ctypes/DLL access goes through ``_load_vigem_dll()``, which
tests mock. The ``XUSB_REPORT`` struct and button constants are module-level so
tests can assert against them without a real DLL.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

# ── ViGEm error codes (from Client.h) ────────────────────────────────────────
VIGEM_ERROR_NONE = 0x20000000

# ── XUSB_BUTTON bitmask values (from Common.h) ───────────────────────────────
XUSB_GAMEPAD_DPAD_UP        = 0x0001
XUSB_GAMEPAD_DPAD_DOWN      = 0x0002
XUSB_GAMEPAD_DPAD_LEFT      = 0x0004
XUSB_GAMEPAD_DPAD_RIGHT     = 0x0008
XUSB_GAMEPAD_START          = 0x0010
XUSB_GAMEPAD_BACK           = 0x0020
XUSB_GAMEPAD_LEFT_THUMB     = 0x0040
XUSB_GAMEPAD_RIGHT_THUMB    = 0x0080
XUSB_GAMEPAD_LEFT_SHOULDER  = 0x0100
XUSB_GAMEPAD_RIGHT_SHOULDER = 0x0200
XUSB_GAMEPAD_GUIDE          = 0x0400
XUSB_GAMEPAD_A              = 0x1000
XUSB_GAMEPAD_B              = 0x2000
XUSB_GAMEPAD_X              = 0x4000
XUSB_GAMEPAD_Y              = 0x8000


class XUSB_REPORT(ctypes.Structure):
    """XINPUT_GAMEPAD-compatible report struct (from ViGEm Common.h).

    Layout: wButtons(2) + bLeftTrigger(1) + bRightTrigger(1) +
            sThumbLX(2) + sThumbLY(2) + sThumbRX(2) + sThumbRY(2) = 12 bytes.
    """

    _fields_ = [
        ("wButtons",      ctypes.c_ushort),
        ("bLeftTrigger",  ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX",      ctypes.c_short),
        ("sThumbLY",      ctypes.c_short),
        ("sThumbRX",      ctypes.c_short),
        ("sThumbRY",      ctypes.c_short),
    ]


# ── SDL GameController button → XUSB bitmask ──────────────────────────────────
# The watcher forwards *semantic* SDL_GameControllerButton values (stable enum,
# mirrored by gamepad_watcher's BTN_*/DPAD_* constants), so we map them straight
# to XUSB bits. CB_GUIDE is intentionally absent — Guide is forwarded via
# set_guide() as a synthetic pulse, never in real-time (Linux evdev model).
CB_A             = 0
CB_B             = 1
CB_X             = 2
CB_Y             = 3
CB_BACK          = 4
CB_GUIDE         = 5
CB_START         = 6
CB_LEFTSTICK     = 7
CB_RIGHTSTICK    = 8
CB_LEFTSHOULDER  = 9
CB_RIGHTSHOULDER = 10
CB_DPAD_UP       = 11
CB_DPAD_DOWN     = 12
CB_DPAD_LEFT     = 13
CB_DPAD_RIGHT    = 14

_BUTTON_TO_XUSB: dict[int, int] = {
    CB_A:             XUSB_GAMEPAD_A,
    CB_B:             XUSB_GAMEPAD_B,
    CB_X:             XUSB_GAMEPAD_X,
    CB_Y:             XUSB_GAMEPAD_Y,
    CB_BACK:          XUSB_GAMEPAD_BACK,
    CB_START:         XUSB_GAMEPAD_START,
    CB_LEFTSTICK:     XUSB_GAMEPAD_LEFT_THUMB,
    CB_RIGHTSTICK:    XUSB_GAMEPAD_RIGHT_THUMB,
    CB_LEFTSHOULDER:  XUSB_GAMEPAD_LEFT_SHOULDER,
    CB_RIGHTSHOULDER: XUSB_GAMEPAD_RIGHT_SHOULDER,
    CB_DPAD_UP:       XUSB_GAMEPAD_DPAD_UP,
    CB_DPAD_DOWN:     XUSB_GAMEPAD_DPAD_DOWN,
    CB_DPAD_LEFT:     XUSB_GAMEPAD_DPAD_LEFT,
    CB_DPAD_RIGHT:    XUSB_GAMEPAD_DPAD_RIGHT,
}

# ── SDL GameController axis → XUSB_REPORT field name ──────────────────────────
CA_LEFTX        = 0
CA_LEFTY        = 1
CA_RIGHTX       = 2
CA_RIGHTY       = 3
CA_TRIGGERLEFT  = 4
CA_TRIGGERRIGHT = 5

_AXIS_TO_FIELD: dict[int, str] = {
    CA_LEFTX:        "sThumbLX",
    CA_LEFTY:        "sThumbLY",
    CA_RIGHTX:       "sThumbRX",
    CA_RIGHTY:       "sThumbRY",
    CA_TRIGGERLEFT:  "bLeftTrigger",
    CA_TRIGGERRIGHT: "bRightTrigger",
}

# Max magnitude of an SDL trigger axis (0..32767), used to scale to the u8 XUSB
# trigger range.
_TRIGGER_MAX = 32767

# SDL Y sticks are positive=down; XInput expects positive=up, so these axes are
# negated during normalisation.
_Y_AXES = frozenset({CA_LEFTY, CA_RIGHTY})


def _load_vigem_dll() -> ctypes.WinDLL:
    """Locate and load ``ViGEmClient.dll``.

    Searched in: the application directory (``sys.path[0]`` / script dir), the
    current working directory, and the system DLL search path. Raises
    ``OSError`` if the DLL cannot be found or loaded.
    """
    dll_name = "ViGEmClient.dll"

    # Build a list of candidate directories to search explicitly before
    # falling back to the OS search path.
    search_dirs: list[str] = []
    if getattr(sys, "frozen", False):
        search_dirs.append(os.path.dirname(sys.executable))
    search_dirs.append(os.getcwd())
    if sys.path and sys.path[0]:
        search_dirs.append(sys.path[0])

    for directory in search_dirs:
        candidate = os.path.join(directory, dll_name)
        if os.path.isfile(candidate):
            return ctypes.WinDLL(candidate)

    # Last resort: let the OS search the default PATH / System32.
    return ctypes.WinDLL(dll_name)


def _setup_prototypes(dll: ctypes.WinDLL) -> None:
    """Declare ctypes prototypes for the ViGEmClient C API functions.

    Called once after the DLL is loaded; sets argtypes/restypes so ctypes
    performs correct marshalling. Kept separate from ``_load_vigem_dll`` so
    tests can call it on a mock DLL.
    """
    PVIGEM_CLIENT  = ctypes.c_void_p
    PVIGEM_TARGET  = ctypes.c_void_p
    VIGEM_ERROR    = ctypes.c_uint32

    dll.vigem_alloc.restype = PVIGEM_CLIENT
    dll.vigem_alloc.argtypes = []

    dll.vigem_free.restype = None
    dll.vigem_free.argtypes = [PVIGEM_CLIENT]

    dll.vigem_connect.restype = VIGEM_ERROR
    dll.vigem_connect.argtypes = [PVIGEM_CLIENT]

    dll.vigem_disconnect.restype = None
    dll.vigem_disconnect.argtypes = [PVIGEM_CLIENT]

    dll.vigem_target_x360_alloc.restype = PVIGEM_TARGET
    dll.vigem_target_x360_alloc.argtypes = []

    dll.vigem_target_free.restype = None
    dll.vigem_target_free.argtypes = [PVIGEM_TARGET]

    dll.vigem_target_add.restype = VIGEM_ERROR
    dll.vigem_target_add.argtypes = [PVIGEM_CLIENT, PVIGEM_TARGET]

    dll.vigem_target_remove.restype = VIGEM_ERROR
    dll.vigem_target_remove.argtypes = [PVIGEM_CLIENT, PVIGEM_TARGET]

    dll.vigem_target_x360_update.restype = VIGEM_ERROR
    dll.vigem_target_x360_update.argtypes = [
        PVIGEM_CLIENT, PVIGEM_TARGET, XUSB_REPORT,
    ]


class VigemWriter:
    """Write to a virtual Xbox360 gamepad through ViGEmBus.

    The writer owns a ``VigemClient`` connection and one ``Xbox360`` target.
    It tracks the full pad state in an internal ``XUSB_REPORT`` and flushes
    the complete report on every change — ViGEmBus applies the diff server-
    side, so sending the full state is cheap and avoids missed updates.

    Usage::

        writer = VigemWriter()
        writer.connect()
        writer.write_button(CB_A, 1)            # press A
        writer.write_button(CB_A, 0)            # release A
        writer.set_guide(True)                  # synthetic guide press
        writer.set_guide(False)                 # synthetic guide release
        writer.disconnect()
    """

    def __init__(self, name: str = "kasual-vpad") -> None:
        self._name = name
        self._dll: ctypes.WinDLL | None = None
        self._client: int | None = None   # PVIGEM_CLIENT (opaque pointer)
        self._target: int | None = None   # PVIGEM_TARGET (opaque pointer)
        self._report = XUSB_REPORT()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Load the DLL, connect to the bus, and plug in the virtual pad.

        Raises ``OSError`` if the DLL cannot be loaded, or ``RuntimeError`` if
        the bus driver is absent or the target cannot be added.
        """
        self._dll = _load_vigem_dll()
        _setup_prototypes(self._dll)

        self._client = self._dll.vigem_alloc()
        if not self._client:
            raise RuntimeError("vigem_alloc() returned NULL")

        err = self._dll.vigem_connect(self._client)
        if err != VIGEM_ERROR_NONE:
            self._dll.vigem_free(self._client)
            self._client = None
            raise RuntimeError(f"vigem_connect() failed: 0x{err:08X}")

        self._target = self._dll.vigem_target_x360_alloc()
        if not self._target:
            self._dll.vigem_disconnect(self._client)
            self._dll.vigem_free(self._client)
            self._client = None
            raise RuntimeError("vigem_target_x360_alloc() returned NULL")

        err = self._dll.vigem_target_add(self._client, self._target)
        if err != VIGEM_ERROR_NONE:
            self._dll.vigem_target_free(self._target)
            self._target = None
            self._dll.vigem_disconnect(self._client)
            self._dll.vigem_free(self._client)
            self._client = None
            raise RuntimeError(f"vigem_target_add() failed: 0x{err:08X}")

        logger.info("ViGEm virtual pad '%s' connected (Xbox360)", self._name)

    def disconnect(self) -> None:
        """Unplug the virtual pad and disconnect from the bus.

        Safe to call multiple times; subsequent calls are no-ops. Swallows
        ctypes errors so shutdown never raises even if the DLL was unloaded.
        """
        if self._dll is None:
            return
        if self._target is not None:
            if self._client is not None:
                try:
                    self._dll.vigem_target_remove(self._client, self._target)
                except Exception:
                    pass
            try:
                self._dll.vigem_target_free(self._target)
            except Exception:
                pass
            self._target = None
        if self._client is not None:
            try:
                self._dll.vigem_disconnect(self._client)
            except Exception:
                pass
            try:
                self._dll.vigem_free(self._client)
            except Exception:
                pass
            self._client = None
        self._report = XUSB_REPORT()
        logger.info("ViGEm virtual pad '%s' disconnected", self._name)

    # ── Event-style writes (mirror evdev semantics) ────────────────────────

    def write_button(self, button: int, value: int) -> None:
        """Set or clear a button by SDL GameController button value.

        ``button`` is a semantic SDL_GameControllerButton value (0=A, 1=B, …,
        11-14 = D-pad). ``value`` is 1 for press, 0 for release. Buttons not in
        the mapping (e.g. Guide) are silently ignored — Guide goes through
        :meth:`set_guide`. The D-pad arrives here as discrete buttons (the
        GameController API never reports it as a hat).
        """
        mask = _BUTTON_TO_XUSB.get(button)
        if mask is None:
            return
        if value:
            self._report.wButtons |= mask
        else:
            self._report.wButtons &= ~mask
        self._flush()

    def write_axis(self, axis: int, value: int) -> None:
        """Set an axis by SDL GameController axis value.

        ``axis`` is a semantic axis value (0=LX, 1=LY, 2=RX, 3=RY, 4=LT, 5=RT).
        ``value`` is the raw SDL int16: -32768..32767 for sticks, 0..32767 for
        triggers. Sticks pass through to the s16 XUSB range (Y inverted, since
        SDL uses positive=down while XInput uses positive=up); triggers scale to
        the u8 (0..255) XUSB range.
        """
        field = _AXIS_TO_FIELD.get(axis)
        if field is None:
            return
        if field.startswith("sThumb"):
            normalised = -value if axis in _Y_AXES else value
            setattr(self._report, field, _clamp_s16(normalised))
        else:
            # Trigger: SDL 0..32767 → 0..255.
            setattr(self._report, field, _clamp_u8(round(value * 255 / _TRIGGER_MAX)))
        self._flush()

    def set_guide(self, value: bool) -> None:
        """Set or clear the Guide (Xbox/Home) button — used for the synthetic
        BTN_MODE forward on short press (mirrors the Linux evdev model)."""
        if value:
            self._report.wButtons |= XUSB_GAMEPAD_GUIDE
        else:
            self._report.wButtons &= ~XUSB_GAMEPAD_GUIDE
        self._flush()

    def reset(self) -> None:
        """Release everything: zero the whole report and flush.

        Used when Kasual's UI takes over (forwarding stops mid-input) so the
        virtual pad doesn't leave a button or stick latched down under the
        foreground app."""
        self._report = XUSB_REPORT()
        self._flush()

    def syn(self) -> None:
        """No-op — ViGEmBus applies the full report immediately on update;
        there is no SYN_REPORT batch commit like evdev."""
        pass

    # ── Internal ───────────────────────────────────────────────────────────

    def _flush(self) -> None:
        """Send the current report to the virtual pad."""
        if self._client is not None and self._target is not None:
            self._dll.vigem_target_x360_update(self._client, self._target, self._report)

    # ── Introspection (for tests) ──────────────────────────────────────────

    @property
    def report(self) -> XUSB_REPORT:
        """The current XUSB_REPORT state (for test assertions)."""
        return self._report

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._target is not None


def _clamp_s16(value: int) -> int:
    return max(-32768, min(32767, value))


def _clamp_u8(value: int) -> int:
    return max(0, min(255, value))
