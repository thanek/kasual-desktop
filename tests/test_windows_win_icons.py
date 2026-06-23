"""Tests for the Windows jumbo-icon extractor (win_icons.py).

Pulls the 256px "jumbo" shell icon via the Win32 image-list API. The chain:
``SHGetFileInfoW`` (resolve the system image-list index) → ``SHGetImageList``
(grab the jumbo image list) → ``ImageList_GetIcon`` (HICON) → ``GetIconInfo`` +
``GetDIBits`` (HICON → QImage). ``DestroyIcon`` and ``DeleteObject`` free the
GDI handles in finally.

Skipped on non-Windows: ``ctypes.windll.shell32``/``comctl32``/``user32``/
``gdi32`` are Windows-only.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only test; needs ctypes.windll", allow_module_level=True)

from infrastructure.windows.win_icons import (
    SHIL_EXTRALARGE, SHIL_JUMBO, jumbo_icon,
)


@pytest.fixture
def mocks():
    """Patch every Win32 binding and ctypes helper the extractor touches.

    Returns a dict of the mock objects so individual tests can wire up the
    chain via ``_setup_chain``. ``ctypes.c_void_p`` is patched so the
    ``himl = ctypes.c_void_p()`` in the production code is truthy (a real
    c_void_p() with no value is falsy, which would short-circuit the
    ``not himl`` check before the mock can act)."""
    patches = [
        patch("infrastructure.windows.win_icons._shell32"),
        patch("infrastructure.windows.win_icons._comctl32"),
        patch("infrastructure.windows.win_icons._user32"),
        patch("infrastructure.windows.win_icons._gdi32"),
        patch("infrastructure.windows.win_icons.ctypes.byref", lambda o: o),
        patch("infrastructure.windows.win_icons.ctypes.sizeof", return_value=64),
        patch("infrastructure.windows.win_icons.ctypes.c_void_p",
              return_value=MagicMock(__bool__=lambda self: True)),
        patch("infrastructure.windows.win_icons._SHFILEINFOW"),
        patch("infrastructure.windows.win_icons._ICONINFO"),
        patch("infrastructure.windows.win_icons._BITMAP"),
        patch("infrastructure.windows.win_icons._BITMAPINFOHEADER"),
    ]
    for p in patches:
        p.start()
    yield {
        "shell32": __import__("infrastructure.windows.win_icons",
                              fromlist=["_shell32"])._shell32,
        "comctl32": __import__("infrastructure.windows.win_icons",
                               fromlist=["_comctl32"])._comctl32,
        "user32": __import__("infrastructure.windows.win_icons",
                             fromlist=["_user32"])._user32,
        "gdi32": __import__("infrastructure.windows.win_icons",
                            fromlist=["_gdi32"])._gdi32,
    }
    for p in patches:
        p.stop()


def _setup_chain(m, *, width=256, height=256, scanned=256, shfi_ok=True,
                 himl_ok=True, hicon=0x200, get_icon_info_ok=True,
                 get_dibits_ok=True):
    """Wire up the full icon-extraction chain with canned success values."""
    m["shell32"].SHGetFileInfoW.return_value = 1 if shfi_ok else 0
    m["shell32"].SHGetImageList.return_value = 0 if himl_ok else 1
    m["comctl32"].ImageList_GetIcon.return_value = hicon
    m["user32"].GetIconInfo.return_value = 1 if get_icon_info_ok else 0
    m["user32"].DestroyIcon.return_value = 1
    m["user32"].GetDC.return_value = 0x10
    m["user32"].ReleaseDC.return_value = 1
    m["gdi32"].GetObjectW.return_value = 1
    m["gdi32"].GetDIBits.return_value = scanned if get_dibits_ok else 0
    m["gdi32"].DeleteObject.return_value = 1
    # The BITMAP struct is read after GetObjectW; the mock fills bmWidth /
    # bmHeight via the byref'd pointer.
    def _get_obj(handle, count, buf):
        buf.bmWidth = width
        buf.bmHeight = height
        return 1
    m["gdi32"].GetObjectW.side_effect = _get_obj


class TestJumboIcon:
    def test_returns_qicon_on_success(self, mocks):
        _setup_chain(mocks)
        icon = jumbo_icon("C:\\app.exe")
        assert icon is not None
        assert not icon.isNull()

    def test_returns_none_when_shgetfileinfo_fails(self, mocks):
        _setup_chain(mocks, shfi_ok=False)
        assert jumbo_icon("C:\\app.exe") is None

    def test_returns_none_when_shgetimagelist_fails(self, mocks):
        _setup_chain(mocks, himl_ok=False)
        assert jumbo_icon("C:\\app.exe") is None

    def test_returns_none_when_hicon_null(self, mocks):
        _setup_chain(mocks, hicon=0)
        assert jumbo_icon("C:\\app.exe") is None

    def test_returns_none_when_get_icon_info_fails(self, mocks):
        _setup_chain(mocks, get_icon_info_ok=False)
        assert jumbo_icon("C:\\app.exe") is None

    def test_returns_none_when_bitmap_dimensions_invalid(self, mocks):
        _setup_chain(mocks, width=0, height=0)
        assert jumbo_icon("C:\\app.exe") is None

    def test_returns_none_when_getdibits_fails(self, mocks):
        _setup_chain(mocks, get_dibits_ok=False)
        assert jumbo_icon("C:\\app.exe") is None

    def test_destroy_icon_called_in_finally(self, mocks):
        # DestroyIcon must be called even when the downstream conversion fails.
        _setup_chain(mocks, get_icon_info_ok=False)
        jumbo_icon("C:\\app.exe")
        mocks["user32"].DestroyIcon.assert_called_once()

    def test_delete_object_called_for_color_and_mask(self, mocks):
        # On the success path, both hbmColor and hbmMask are freed.
        _setup_chain(mocks)
        # Make the ICONINFO instance report non-null hbmColor / hbmMask.
        from infrastructure.windows.win_icons import _ICONINFO
        info = MagicMock()
        info.hbmColor = 0x300
        info.hbmMask = 0x400
        _ICONINFO.return_value = info
        jumbo_icon("C:\\app.exe")
        deleted = [c.args[0] for c in mocks["gdi32"].DeleteObject.call_args_list]
        assert 0x300 in deleted
        assert 0x400 in deleted

    def test_shil_extralarge_supported(self, mocks):
        # The default shil is SHIL_JUMBO; passing SHIL_EXTRALARGE (48px) also
        # works and is forwarded to SHGetImageList.
        _setup_chain(mocks)
        icon = jumbo_icon("C:\\app.exe", shil=SHIL_EXTRALARGE)
        assert icon is not None
        # SHGetImageList's first arg is the shil flag.
        assert mocks["shell32"].SHGetImageList.call_args.args[0] == SHIL_EXTRALARGE

    def test_exception_returns_none(self, mocks):
        # Any unexpected exception is caught and returns None (best-effort).
        mocks["shell32"].SHGetFileInfoW.side_effect = OSError("access denied")
        assert jumbo_icon("C:\\app.exe") is None


class TestShilConstants:
    def test_jumbo_is_4(self):
        assert SHIL_JUMBO == 0x4

    def test_extralarge_is_2(self):
        assert SHIL_EXTRALARGE == 0x2
