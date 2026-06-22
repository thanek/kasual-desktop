"""Extract large (256px "jumbo") icons for files via the Win32 shell image list.

Qt's ``QFileIconProvider`` only hands back the 32px shell icon on Windows (it
reports larger sizes but never delivers their pixels), so tiles looked tiny. Here
we pull the real 256px jumbo icon: resolve the file's system image-list index,
fetch the jumbo image list, grab the HICON, and convert it to a QImage.

No pywin32 / COM-vtable juggling needed — ``SHGetImageList`` returns an
``IImageList*`` that doubles as a legacy ``HIMAGELIST`` for ``ImageList_GetIcon``.
"""

import ctypes
import logging
from ctypes import wintypes

from PyQt6.QtGui import QIcon, QImage, QPixmap

logger = logging.getLogger(__name__)

SHGFI_SYSICONINDEX = 0x000004000
SHIL_JUMBO = 0x4
SHIL_EXTRALARGE = 0x2
ILD_TRANSPARENT = 0x1


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


# IID_IImageList {46EB5926-582E-4017-9FDF-E8998DAA0950}
_IID_IImageList = _GUID(0x46EB5926, 0x582E, 0x4017,
                        (ctypes.c_byte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))

_shell32 = ctypes.windll.shell32
_comctl32 = ctypes.windll.comctl32
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

_shell32.SHGetFileInfoW.restype = ctypes.c_void_p
_shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.POINTER(_SHFILEINFOW), wintypes.UINT, wintypes.UINT]
_shell32.SHGetImageList.restype = ctypes.c_long
_shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
_comctl32.ImageList_GetIcon.restype = ctypes.c_void_p
_comctl32.ImageList_GetIcon.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.UINT]
_user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ICONINFO)]
_user32.DestroyIcon.argtypes = [ctypes.c_void_p]
_user32.GetDC.restype = ctypes.c_void_p
_user32.GetDC.argtypes = [ctypes.c_void_p]
_user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
_gdi32.DeleteObject.argtypes = [ctypes.c_void_p]


def jumbo_icon(path: str, shil: int = SHIL_JUMBO) -> QIcon | None:
    """A QIcon built from *path*'s 256px shell icon, or None on failure."""
    try:
        image = _jumbo_image(path, shil)
    except Exception as exc:
        logger.debug("jumbo_icon failed for %s: %s", path, exc)
        return None
    if image is None or image.isNull():
        return None
    return QIcon(QPixmap.fromImage(image))


def _jumbo_image(path: str, shil: int) -> QImage | None:
    shfi = _SHFILEINFOW()
    if not _shell32.SHGetFileInfoW(path, 0, ctypes.byref(shfi),
                                   ctypes.sizeof(shfi), SHGFI_SYSICONINDEX):
        return None
    himl = ctypes.c_void_p()
    if _shell32.SHGetImageList(shil, ctypes.byref(_IID_IImageList), ctypes.byref(himl)) != 0 or not himl:
        return None
    hicon = _comctl32.ImageList_GetIcon(himl, shfi.iIcon, ILD_TRANSPARENT)
    if not hicon:
        return None
    try:
        return _hicon_to_image(hicon)
    finally:
        _user32.DestroyIcon(hicon)


def _hicon_to_image(hicon: int) -> QImage | None:
    info = _ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    try:
        bm = _BITMAP()
        _gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        if w <= 0 or h <= 0:
            return None

        hdr = _BITMAPINFOHEADER()
        hdr.biSize = ctypes.sizeof(hdr)
        hdr.biWidth = w
        hdr.biHeight = -h          # top-down
        hdr.biPlanes = 1
        hdr.biBitCount = 32
        hdr.biCompression = 0      # BI_RGB
        buf = (ctypes.c_byte * (w * h * 4))()
        hdc = _user32.GetDC(None)
        try:
            scanned = _gdi32.GetDIBits(hdc, info.hbmColor, 0, h, buf, ctypes.byref(hdr), 0)
        finally:
            _user32.ReleaseDC(None, hdc)
        if not scanned:
            return None
        # GetDIBits gives BGRA, which matches QImage.Format_ARGB32 in memory on
        # little-endian. Copy so the QImage owns its bytes after buf is freed.
        return QImage(bytes(buf), w, h, QImage.Format.Format_ARGB32).copy()
    finally:
        if info.hbmColor:
            _gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            _gdi32.DeleteObject(info.hbmMask)
