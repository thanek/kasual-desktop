"""WindowsRtssHudControl — the :class:`HudControl` port over RivaTuner Statistics
Server's runtime OSD-visibility flag.

The in-game performance HUD on Windows is RTSS's On-Screen Display (driven by MSI
Afterburner or RTSS itself). RTSS exposes a runtime flags word through the
``SetFlags(dwAND, dwXOR)`` export of ``RTSSHooks64.dll`` — the very mechanism its
own *Show OSD On/Off/Toggle* hotkeys use (see the RTSS SDK HotkeyHandler sample,
``OnOSDOn``/``OnOSDOff``). ``SetFlags`` mutates the word as ``(word & dwAND) ^
dwXOR`` and returns the result, so bit ``RTSSHOOKSFLAG_OSD_VISIBLE`` (0x1) — the
global OSD on/off — is read and flipped directly:

  - **read**    ⟺ ``SetFlags(0xFFFFFFFF, 0)`` returns the word unchanged;
  - **enable**  → ``SetFlags(~OSD_VISIBLE, OSD_VISIBLE)`` (clear then set the bit);
  - **disable** → ``SetFlags(~OSD_VISIBLE, 0)`` (clear the bit).

This is the Windows analogue of :class:`infrastructure.linux.hud.mangohud.MangoHudControl`:
it needs no elevation and writes no files, and — unlike the persistent ``EnableOSD``
profile property whose only writable copy lives under RTSS's ``Program Files``
folder — it reflects the live state, so the toggle's label is always accurate. The
flag is *runtime* visibility (like pressing the OSD hotkey), which is exactly what a
HUD toggle wants.

The whole feature is gated on RTSS running: with no RTSS process there is no flags
word to read, so the toggle is never offered (``is_available``). The DLL access sits
behind the :class:`_RtssFlags` seam so the bit logic is unit-testable without RTSS
installed.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from pathlib import Path
from typing import Protocol

from domain.system.hud import HudControl

logger = logging.getLogger(__name__)

# RTSS SDK: RTSSHooksInterface.h. The OSD on/off bit of the runtime flags word.
RTSSHOOKSFLAG_OSD_VISIBLE = 0x00000001
_MASK32 = 0xFFFFFFFF
_DLL_NAME = "RTSSHooks64.dll"


class _RtssFlags(Protocol):
    """Seam onto RTSS's runtime flags word (the ``SetFlags`` export).

    ``read`` and ``write`` return ``None`` when RTSS is unreachable (not running
    / DLL missing), which ``available`` reports up front."""

    def available(self) -> bool: ...
    def read(self) -> int | None: ...
    def write(self, and_mask: int, xor_mask: int) -> int | None: ...


class _DllRtssFlags(_RtssFlags):
    """``SetFlags`` via ``RTSSHooks64.dll``, located next to the running RTSS.exe."""

    def __init__(self) -> None:
        self._setflags = None  # resolved SetFlags func, cached while RTSS is up

    def available(self) -> bool:
        return self._resolve() is not None

    def read(self) -> int | None:
        return self._call(_MASK32, 0)

    def write(self, and_mask: int, xor_mask: int) -> int | None:
        return self._call(and_mask & _MASK32, xor_mask & _MASK32)

    def _call(self, and_mask: int, xor_mask: int) -> int | None:
        fn = self._resolve()
        if fn is None:
            return None
        try:
            return int(fn(and_mask, xor_mask)) & _MASK32
        except OSError as exc:
            logger.warning("RTSS SetFlags(%#x, %#x) failed: %s", and_mask, xor_mask, exc)
            return None

    def _resolve(self):
        """Resolve ``SetFlags``, re-checking that RTSS is running each call.

        The function is cached only while an RTSS process is alive, so the feature
        appears/disappears as RTSS is started/stopped between Home Overlay opens
        (mirrors MangoHud's live config-file check)."""
        dll_path = _rtss_hooks_path()
        if dll_path is None:
            self._setflags = None
            return None
        if self._setflags is None:
            try:
                fn = ctypes.CDLL(str(dll_path)).SetFlags
                fn.argtypes = [wintypes.DWORD, wintypes.DWORD]
                fn.restype = wintypes.DWORD
                self._setflags = fn
            except (OSError, AttributeError) as exc:
                logger.warning("Could not bind %s SetFlags: %s", _DLL_NAME, exc)
                return None
        return self._setflags


def _rtss_hooks_path() -> Path | None:
    """Path to ``RTSSHooks64.dll`` beside the running RTSS.exe, or ``None`` when
    RTSS is not running or the DLL is missing."""
    try:
        import psutil
    except Exception:
        return None
    try:
        procs = psutil.process_iter(["name", "exe"])
    except Exception:
        return None
    for proc in procs:
        if (proc.info.get("name") or "").lower() == "rtss.exe":
            exe = proc.info.get("exe")
            if exe:
                dll = Path(exe).with_name(_DLL_NAME)
                return dll if dll.is_file() else None
    return None


class WindowsRtssHudControl(HudControl):
    def __init__(self, flags: _RtssFlags | None = None) -> None:
        self._flags = flags if flags is not None else _DllRtssFlags()

    def is_available(self) -> bool:
        return self._flags.available()

    def is_enabled(self) -> bool:
        word = self._flags.read()
        return word is not None and bool(word & RTSSHOOKSFLAG_OSD_VISIBLE)

    def enable(self) -> None:
        # clear the OSD bit, then set it — independent of the prior state
        self._flags.write(~RTSSHOOKSFLAG_OSD_VISIBLE, RTSSHOOKSFLAG_OSD_VISIBLE)

    def disable(self) -> None:
        self._flags.write(~RTSSHOOKSFLAG_OSD_VISIBLE, 0)  # clear the OSD bit
