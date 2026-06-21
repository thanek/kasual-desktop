"""Pin an open window as a persistent Kasual app tile — Windows AppPinning adapter.

Mirrors the Linux ``DesktopAppPinning`` but resolves the window's *source*
differently. Linux looks up the window's freedesktop ``.desktop`` in the system
app dirs; Windows has no such registry, so we derive a launchable :class:`App`
straight from the window's process:

  - ``command`` — the process's full executable path (WindowsAppManager launches it);
  - ``name``    — the exe's version-info *FileDescription* (e.g. "Microsoft Edge"),
                  falling back to the exe basename, then the window title;
  - ``wm_class``— the exe basename (the window's ``resource_class``), so the pinned
                  tile matches its running window back (reads as running, restores
                  instead of launching a duplicate).

Everything else — writing/numbering/deleting the catalog ``.desktop`` files —
is reused from the Linux adapter and ``app_config``.
"""

import ctypes
import logging
import struct

from domain.catalog.app import App
from domain.catalog.window import Window

from infrastructure.system.app_config import apps_dir, _write_desktop
from infrastructure.system.app_pinning import DesktopAppPinning
from infrastructure.windows.window_manager import _get_exe_path

logger = logging.getLogger(__name__)


class WindowsAppPinning(DesktopAppPinning):
    """Resolve a window to an :class:`App` via its process, then persist it.

    Reuses the base class for ``unpin`` and the file placement helpers
    (``_next_order``/``_unique_path``); only ``pin``'s source resolution differs.
    """

    def pin(self, window: Window) -> App | None:
        exe = _get_exe_path(window.pid) if window.pid else None
        if not exe:
            logger.warning(
                "Pin: cannot resolve exe for window (pid=%s class=%r)",
                window.pid, window.resource_class,
            )
            return None

        name = (
            _file_description(exe)
            or (window.resource_class.title() if window.resource_class else None)
            or (window.title.strip() if window.title else None)
            or "App"
        )
        app = App(name=name, command=exe, wm_class=window.resource_class or None)

        directory = apps_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Pin: cannot create apps dir %s: %s", directory, exc)
            return None

        order = self._next_order(directory)
        path = self._unique_path(directory, window, app)
        try:
            _write_desktop(path, app.to_desktop_entry(order))
        except OSError as exc:
            logger.error("Pin: cannot write %s: %s", path, exc)
            return None

        logger.info("Pinned %r to %s", app.name, path.name)
        return app


def _file_description(exe_path: str) -> str | None:
    """The exe's version-info FileDescription (the friendly app name), or None.

    Reads the PE version resource via the Win32 version API — the same string
    Explorer shows as an app's display name (e.g. "Microsoft Edge")."""
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(exe_path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(exe_path, 0, size, buf):
            return None

        ptr = ctypes.c_void_p()
        length = ctypes.c_uint()
        # Pick the first language/codepage the file declares.
        if not ver.VerQueryValueW(buf, r"\VarFileInfo\Translation",
                                  ctypes.byref(ptr), ctypes.byref(length)) or not length.value:
            return None
        lang, codepage = struct.unpack("HH", ctypes.string_at(ptr.value, 4))

        sub = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        if not ver.VerQueryValueW(buf, sub, ctypes.byref(ptr), ctypes.byref(length)) or not length.value:
            return None
        desc = ctypes.wstring_at(ptr.value, length.value).strip("\x00").strip()
        return desc or None
    except Exception:
        return None
