"""HidHide control client — hide physical HID devices from non-whitelisted apps.

Talks to the HidHide kernel filter driver through its control device
``\\\\.\\HidHide`` using ``DeviceIoControl`` with the IOCTL contract from
``HidHideIoctlContract.h``. This is the authoritative, stable ABI (the plan's
section 4 mentioned COM/registry as alternatives, but the real driver contract
is IOCTL-based — the CLI tool ``HidHideControl.exe`` uses the same calls).

Operations:
  - **Whitelist** — full NT image paths of processes allowed to see hidden
    devices. Kasual adds its own image path (``python.exe`` / ``kasual.exe``)
    so its pygame/SDL input still sees the physical gamepad.
  - **Blacklist** — device instance paths of HID devices to hide. Kasual adds
    the physical gamepad's instance path so Steam/games/bundled-apps no longer
    see it (they see the virtual ``kasual-vpad`` instead).
  - **Active** — whether the filter is currently cloaking. Set to True when
    Kasual starts hiding, left as-is on shutdown (other apps like DS4Windows
    may depend on it).

Device instance path resolution (the hardest piece, per plan section 7/13):
``resolve_gamepad_instance_ids`` uses SetupAPI to enumerate present HID
devices and filters to gamepad/joystick usage (page 0x01, usage 0x04/0x05),
returning their instance paths (e.g. ``HID\\VID_045E&PID_02FD&…\\7&…``).

Testability: every Win32 call goes through small module-level functions that
tests monkeypatch (``_create_file``, ``_device_io_control``, ``_query_dos_device``,
``_enum_hid_gamepads``). The :class:`HidHideClient` methods are pure orchestration
on top of them.
"""

from __future__ import annotations

import logging
import os
import sys
import ctypes
from ctypes import wintypes

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

HIDHIDE_CONTROL_DEVICE = r"\\.\HidHide"

# IOCTL device type and codes (from HidHideIoctlContract.h).
#   CTL_CODE(DeviceType, Function, METHOD_BUFFERED=0, FILE_READ_DATA=1)
#   = (DeviceType << 16) | (1 << 14) | (Function << 2)
_IOCTL_DEVICE_TYPE = 32769


def _ctl_code(function: int) -> int:
    return (_IOCTL_DEVICE_TYPE << 16) | (1 << 14) | (function << 2)


IOCTL_GET_WHITELIST = _ctl_code(2048)
IOCTL_SET_WHITELIST = _ctl_code(2049)
IOCTL_GET_BLACKLIST = _ctl_code(2050)
IOCTL_SET_BLACKLIST = _ctl_code(2051)
IOCTL_GET_ACTIVE    = _ctl_code(2052)
IOCTL_SET_ACTIVE    = _ctl_code(2053)
IOCTL_GET_WLINVERSE = _ctl_code(2054)
IOCTL_SET_WLINVERSE = _ctl_code(2055)

# HID class GUID: {745A17A0-74D3-11D0-B6FE-00A0C90F57DA}
HID_CLASS_GUID = "745A17A0-74D3-11D0-B6FE-00A0C90F57DA"

GENERIC_READ       = 0x80000000
GENERIC_WRITE      = 0x40000000
FILE_SHARE_ALL     = 0x07  # READ | WRITE | DELETE
OPEN_EXISTING      = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED  = 5


# ── Win32 ctypes bindings ────────────────────────────────────────────────────

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_hid      = ctypes.WinDLL("hid", use_last_error=True)

# CreateFileW
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]

# CloseHandle
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

# DeviceIoControl
_kernel32.DeviceIoControl.restype = wintypes.BOOL
_kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]

# QueryDosDeviceW
_kernel32.QueryDosDeviceW.restype = wintypes.DWORD
_kernel32.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]


# ── Low-level wrappers (monkey-patched in tests) ─────────────────────────────

def _create_file(path: str, access: int, share: int) -> int:
    """Open the HidHide control device. Returns a handle or raises OSError."""
    handle = _kernel32.CreateFileW(
        path, access, share, None, OPEN_EXISTING, 0, None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), f"CreateFileW failed for {path}")
    return handle


def _device_io_control(
    handle: int, ioctl: int, in_buf: bytes | None, out_size: int,
) -> bytes:
    """Send an IOCTL and return the output buffer contents.

    For GET IOCTLs with variable-size output, use :func:`_device_io_control_get`
    which handles the two-phase query-size-then-read pattern.
    """
    out_buf = ctypes.create_string_buffer(out_size)
    bytes_returned = wintypes.DWORD(0)
    in_ptr: ctypes.c_void_p | None = None
    in_size = 0
    if in_buf is not None:
        in_ptr = ctypes.cast(
            ctypes.create_string_buffer(in_buf, len(in_buf)),
            ctypes.c_void_p,
        )
        in_size = len(in_buf)
    ok = _kernel32.DeviceIoControl(
        handle, ioctl, in_ptr, in_size,
        out_buf, out_size, ctypes.byref(bytes_returned), None,
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), f"DeviceIoControl {ioctl:#x} failed")
    return bytes(out_buf.raw[:bytes_returned.value])


def _device_io_control_get(handle: int, ioctl: int) -> bytes:
    """Two-phase GET: query the needed size, then read the full buffer.

    HidHide's GET IOCTLs return TRUE even with a zero-size output buffer,
    writing the required byte count into *bytes_returned*. We then allocate
    that size and re-issue the IOCTL to get the actual data.
    """
    bytes_returned = wintypes.DWORD(0)
    ok = _kernel32.DeviceIoControl(
        handle, ioctl, None, 0, None, 0, ctypes.byref(bytes_returned), None,
    )
    if not ok:
        # Some driver versions return FALSE with ERROR_INSUFFICIENT_BUFFER
        # but still set bytes_returned; others return TRUE. Handle both.
        err = ctypes.get_last_error()
        if err != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise OSError(err, f"DeviceIoControl {ioctl:#x} size query failed")
    needed = bytes_returned.value
    if needed == 0:
        return b""
    return _device_io_control(handle, ioctl, None, needed)


def _query_dos_device(drive_letter: str) -> str:
    """Convert a drive letter (e.g. 'C:') to its NT device path."""
    buf = ctypes.create_unicode_buffer(512)
    length = _kernel32.QueryDosDeviceW(drive_letter, buf, 512)
    if not length:
        raise OSError(ctypes.get_last_error(), f"QueryDosDeviceW failed for {drive_letter}")
    return buf.value


# ── Multi-string helpers ─────────────────────────────────────────────────────

def _multi_string_to_list(data: bytes) -> list[str]:
    """Decode a REG_MULTI_SZ-style buffer (UTF-16LE, null-terminated strings,
    terminated by an extra null) into a list of strings."""
    # The buffer is a sequence of UTF-16LE strings, each null-terminated,
    # followed by a final null terminator (empty string).
    decoded = data.decode("utf-16-le", errors="replace")
    parts = decoded.split("\x00")
    # Drop the trailing empty strings (the final terminator produces them).
    return [p for p in parts if p]


def _list_to_multi_string(strings: list[str]) -> bytes:
    """Encode a list of strings into a REG_MULTI_SZ-style UTF-16LE buffer."""
    # Each string null-terminated, then a final null terminator.
    return "".join(s + "\x00" for s in strings).encode("utf-16-le") + "\x00".encode("utf-16-le")


# ── Win32 path → NT image path conversion ────────────────────────────────────

def win32_to_nt_path(win32_path: str) -> str:
    """Convert a Win32 path (``C:\\Users\\...``) to an NT image path
    (``\\Device\\HarddiskVolume3\\Users\\...``).

    HidHide's whitelist stores full NT image paths — the kernel matches
    processes by their NT path, not the Win32 drive-letter path.
    """
    if len(win32_path) < 2 or win32_path[1] != ":":
        return win32_path  # Already an NT path or UNC; return as-is.
    drive = win32_path[:2]  # e.g. "C:"
    nt_prefix = _query_dos_device(drive)
    return nt_prefix + win32_path[2:]


def current_process_image_path() -> str:
    """The NT image path of the current process (for the HidHide whitelist)."""
    win32_path = sys.executable  # e.g. C:\Python311\python.exe
    return win32_to_nt_path(win32_path)


# ── SetupAPI: gamepad device instance path resolution ────────────────────────

# SetupAPI function prototypes
_setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
_setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
]

_setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
_setupapi.SetupDiEnumDeviceInfo.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
]

_setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
_setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]

_setupapi.SetupDiDestroyDeviceInfoList.restype = None
_setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

# Flags
DIGCF_PRESENT     = 0x02
DIGCF_DEVICEINTERFACE = 0x10

# HidD_GetAttributes / HidD_GetHidGuid
class _HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


_hid.HidD_GetAttributes.restype = wintypes.BOOL
_hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.c_void_p]

_hid.HidD_GetHidGuid.restype = None
_hid.HidD_GetHidGuid.argtypes = [ctypes.c_void_p]

# HidD_GetPreparsedData / HidD_FreePreparsedData / HidP_GetCaps — used to read a
# device's HID usage page/usage so we hide ONLY gamepads, never mice/keyboards
# that happen to share a vendor ID (e.g. Logitech VID_046D, Microsoft VID_045E).
_hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
_hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]

_hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]

_hid.HidP_GetCaps.restype = ctypes.c_long  # NTSTATUS
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

# SetupAPI device-interface enumeration (needed to open each HID device by its
# interface path so we can interrogate its usage page).
_setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
_setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
]

_setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
_setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]

# HID usage page/usage for game controllers (HID Usage Tables §4 Generic Desktop).
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_JOYSTICK     = 0x04
HID_USAGE_GAMEPAD      = 0x05
HIDP_STATUS_SUCCESS    = 0x00110000  # NTSTATUS returned by HidP_GetCaps on success


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", wintypes.BYTE * 16),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),  # ULONG_PTR
    ]


class _HIDP_CAPS(ctypes.Structure):
    """HID capability struct (from hidpi.h). Only Usage/UsagePage are read, but
    the full layout must be declared so HidP_GetCaps does not overflow the
    buffer it writes into."""

    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


# SP_DEVINFO_DATA
class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.ULONG),
        ("ClassGuid", wintypes.BYTE * 16),
        ("DevInst", wintypes.ULONG),
        ("Reserved", ctypes.c_void_p),
    ]


def _enum_hid_gamepads() -> list[str]:
    """Enumerate present HID devices that are gamepads/joysticks.

    Returns their device instance paths (e.g.
    ``HID\\VID_045E&PID_02FD&IG_00\\7&1A2B3C4D&0&0000``).

    Uses SetupAPI to enumerate the HID class, then opens each device interface
    and reads its HID usage page/usage via ``HidP_GetCaps``. Filters to usage
    page 0x01 (Generic Desktop) and usage 0x04 (Joystick) or 0x05 (Gamepad).

    This authoritative usage-page check (rather than a vendor-ID guess) is what
    keeps us from ever blacklisting a mouse or keyboard that shares a vendor ID
    with a gamepad maker (Logitech, Microsoft, etc.) — hiding those would cut
    the user's pointer/keyboard off from every non-whitelisted process. A device
    we cannot open or interrogate is skipped (fail-safe: never hide the unknown).
    """
    # Get the HID interface GUID
    guid_buf = (wintypes.BYTE * 16)()
    _hid.HidD_GetHidGuid(ctypes.byref(guid_buf))

    devs = _setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid_buf), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if not devs:
        return []

    instance_paths: list[str] = []
    try:
        index = 0
        while True:
            iface = _SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(
                devs, None, ctypes.byref(guid_buf), index, ctypes.byref(iface),
            ):
                break  # No more interfaces
            index += 1

            dev_info = _SP_DEVINFO_DATA()
            dev_info.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
            device_path = _get_interface_path(devs, iface, dev_info)
            if not device_path:
                continue

            usage = _hid_usage(device_path)
            if usage is None:
                continue  # Can't interrogate → don't hide it.
            usage_page, usage_id = usage
            if usage_page == HID_USAGE_PAGE_GENERIC and usage_id in (
                HID_USAGE_JOYSTICK, HID_USAGE_GAMEPAD,
            ):
                instance_path = _get_device_instance_id(devs, dev_info)
                if instance_path:
                    instance_paths.append(instance_path)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(devs)

    return instance_paths


def _get_interface_path(devs: int, iface: _SP_DEVICE_INTERFACE_DATA,
                        dev_info: _SP_DEVINFO_DATA) -> str:
    """Resolve a device-interface element to its openable device path.

    Also fills *dev_info* with the owning device node, so the caller can read
    its instance id with :func:`_get_device_instance_id`.
    """
    req = wintypes.DWORD(0)
    # First call: query the required buffer size.
    _setupapi.SetupDiGetDeviceInterfaceDetailW(
        devs, ctypes.byref(iface), None, 0, ctypes.byref(req), None,
    )
    if req.value == 0:
        return ""
    buf = ctypes.create_string_buffer(req.value)
    # cbSize is the size of the FIXED part of SP_DEVICE_INTERFACE_DETAIL_DATA_W:
    # 8 on 64-bit (alignment quirk), 6 on 32-bit. The DevicePath string itself
    # still starts immediately after the DWORD, at byte offset 4.
    cb = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
    ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0] = cb
    if not _setupapi.SetupDiGetDeviceInterfaceDetailW(
        devs, ctypes.byref(iface), buf, req.value, None, ctypes.byref(dev_info),
    ):
        return ""
    return ctypes.wstring_at(ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD))


def _hid_usage(device_path: str) -> tuple[int, int] | None:
    """Return ``(usage_page, usage)`` for a HID device interface path.

    Opens the device with query-only access (0) and shared read/write so it
    never disturbs a device another process already holds. Returns ``None`` on
    any failure (the device cannot be opened/parsed), so callers fail safe.
    """
    handle = _kernel32.CreateFileW(
        device_path, 0, FILE_SHARE_ALL, None, OPEN_EXISTING, 0, None,
    )
    if handle == INVALID_HANDLE_VALUE:
        return None
    try:
        preparsed = ctypes.c_void_p(0)
        if not _hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            return None
        try:
            caps = _HIDP_CAPS()
            if _hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
                return None
            return (caps.UsagePage, caps.Usage)
        finally:
            _hid.HidD_FreePreparsedData(preparsed)
    finally:
        _kernel32.CloseHandle(handle)


def _get_device_instance_id(devs: int, dev_info: _SP_DEVINFO_DATA) -> str:
    """Get the device instance path for a SetupAPI device."""
    size = wintypes.DWORD(0)
    # First call to get the required size.
    _setupapi.SetupDiGetDeviceInstanceIdW(
        devs, ctypes.byref(dev_info), None, 0, ctypes.byref(size),
    )
    if size.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(size.value)
    if not _setupapi.SetupDiGetDeviceInstanceIdW(
        devs, ctypes.byref(dev_info), buf, size.value, None,
    ):
        return ""
    return buf.value


def _is_gamepad_device(instance_path: str) -> bool:
    """Coarse heuristic: does this HID instance path look like a gamepad?

    Checks for the ``HID\\`` prefix and a known gamepad vendor ID. This is NOT
    the device-hiding gate — :func:`_enum_hid_gamepads` interrogates the real
    HID usage page instead, because a vendor ID alone is ambiguous (Logitech and
    Microsoft also make the mice/keyboards we must never hide). Kept as a cheap
    secondary check and for diagnostics.
    """
    upper = instance_path.upper()
    if not upper.startswith("HID\\"):
        return False
    # Known gamepad vendor IDs (Microsoft, Sony, Nintendo, 8BitDo, Logitech,
    # Hori, Razer, Valve, PDP, Mad Catz, SteelSeries, ASUS).
    gamepad_vids = (
        "VID_045E",  # Microsoft (Xbox)
        "VID_054C",  # Sony (PlayStation/DualSense)
        "VID_057E",  # Nintendo
        "VID_2DC8",  # 8BitDo
        "VID_046D",  # Logitech
        "VID_0F0D",  # Hori
        "VID_1532",  # Razer
        "VID_28DE",  # Valve (Steam Deck)
        "VID_0E6F",  # PDP / Afterglow
        "VID_0738",  # Mad Catz
        "VID_0111",  # SteelSeries
        "VID_0B05",  # ASUS
    )
    return any(vid in upper for vid in gamepad_vids)


# ── Client ───────────────────────────────────────────────────────────────────


class HidHideClient:
    """Control the HidHide filter driver.

    Manages the whitelist (processes that can see hidden devices) and the
    blacklist (devices to hide). All operations are idempotent — adding an
    entry that's already present is a no-op.

    The client opens a handle to ``\\\\.\\HidHide`` on construction and closes
    it on :meth:`close`. If the driver is not installed, the constructor
    raises ``OSError`` (caught by the probe).
    """

    def __init__(self) -> None:
        self._handle: int | None = None
        self._blacklisted: set[str] = set()  # instance paths we added
        self._opened = False

    def _open(self) -> None:
        """Open the control device handle (lazy, on first use)."""
        if self._handle is not None:
            return
        self._handle = _create_file(
            HIDHIDE_CONTROL_DEVICE,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_ALL,
        )
        self._opened = True

    def close(self) -> None:
        """Close the control device handle."""
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def ping(self) -> bool:
        """Check if the HidHide driver is reachable (for probe_drivers).

        Closes the handle before returning: HidHide's control device allows only
        a single open handle, so a leaked probe handle makes the later
        register/hide open fail with ERROR_ACCESS_DENIED.
        """
        try:
            self._open()
            self.get_active()
            return True
        except Exception:
            return False
        finally:
            self.close()

    def __del__(self):
        # Defensive: never leave the single-open control handle dangling.
        try:
            self.close()
        except Exception:
            pass

    # ── Whitelist (process image paths) ──────────────────────────────────────

    def get_whitelist(self) -> list[str]:
        """Return the current whitelist (NT image paths)."""
        self._open()
        data = _device_io_control_get(self._handle, IOCTL_GET_WHITELIST)
        return _multi_string_to_list(data)

    def _set_whitelist(self, paths: list[str]) -> None:
        self._open()
        buf = _list_to_multi_string(paths)
        _device_io_control(self._handle, IOCTL_SET_WHITELIST, buf, 0)

    def register_self(self) -> None:
        """Add the current process's image path to the whitelist (idempotent).

        After this call, the Kasual process can see devices hidden by HidHide
        (i.e. the physical gamepad), while non-whitelisted processes (Steam,
        games, bundled apps) cannot.
        """
        current = current_process_image_path()
        wl = self.get_whitelist()
        if current not in wl:
            wl.append(current)
            self._set_whitelist(wl)
        logger.info("HidHide whitelist: registered %s", current)

    def unregister_self(self) -> None:
        """Remove the current process from the whitelist (idempotent)."""
        current = current_process_image_path()
        wl = self.get_whitelist()
        if current in wl:
            wl.remove(current)
            self._set_whitelist(wl)
            logger.info("HidHide whitelist: unregistered %s", current)

    # ── Blacklist (device instance paths) ────────────────────────────────────

    def get_blacklist(self) -> list[str]:
        """Return the current blacklist (device instance paths)."""
        self._open()
        data = _device_io_control_get(self._handle, IOCTL_GET_BLACKLIST)
        return _multi_string_to_list(data)

    def _set_blacklist(self, instance_paths: list[str]) -> None:
        self._open()
        buf = _list_to_multi_string(instance_paths)
        _device_io_control(self._handle, IOCTL_SET_BLACKLIST, buf, 0)

    def hide_device(self, instance_id: str) -> None:
        """Add a device instance path to the blacklist (idempotent)."""
        bl = self.get_blacklist()
        if instance_id not in bl:
            bl.append(instance_id)
            self._set_blacklist(bl)
            self._blacklisted.add(instance_id)
            logger.info("HidHide blacklist: hidden %s", instance_id)

    def unhide_device(self, instance_id: str) -> None:
        """Remove a device instance path from the blacklist (idempotent)."""
        bl = self.get_blacklist()
        if instance_id in bl:
            bl.remove(instance_id)
            self._set_blacklist(bl)
            self._blacklisted.discard(instance_id)
            logger.info("HidHide blacklist: unhidden %s", instance_id)

    def unhide_all(self) -> None:
        """Remove every device we blacklisted (cleanup on shutdown)."""
        for instance_id in list(self._blacklisted):
            self.unhide_device(instance_id)

    # ── Active state ─────────────────────────────────────────────────────────

    def get_active(self) -> bool:
        """Is the filter currently cloaking hidden devices?"""
        self._open()
        data = _device_io_control(self._handle, IOCTL_GET_ACTIVE, None, 1)
        return bool(data[0]) if data else False

    def set_active(self, active: bool) -> None:
        """Enable or disable cloaking."""
        self._open()
        buf = bytes([1 if active else 0])
        _device_io_control(self._handle, IOCTL_SET_ACTIVE, buf, 0)

    # ── Convenience ──────────────────────────────────────────────────────────

    @staticmethod
    def resolve_gamepad_instance_ids() -> list[str]:
        """Find present gamepad HID devices and return their instance paths.

        Used by the watcher to know which device(s) to blacklist. Returns all
        matching devices — the watcher blacklists the one pygame is using (or
        all, for the single-gamepad common case).
        """
        return _enum_hid_gamepads()
