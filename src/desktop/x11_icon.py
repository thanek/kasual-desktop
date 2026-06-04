"""Read a window's embedded icon (_NET_WM_ICON) from XWayland.

This mirrors what the KWin/Plasma task manager falls back to when an app has
no matching .desktop / themed icon: the ARGB pixmap the application embeds in
its own X11 window (`_NET_WM_ICON`). Covers Steam games, Wine/Proton titles and
other XWayland apps whose window class maps to nothing in the icon theme.

Pure-Wayland windows have no `_NET_WM_ICON`; those resolve via name/theme
lookup in :mod:`window_icons` instead. The module degrades gracefully (returns
None) when python-xlib is missing or no X server is reachable.
"""

import array
import logging
import os

logger = logging.getLogger(__name__)


class X11IconReader:
    """Reads `_NET_WM_ICON` ARGB data from XWayland windows, matched by PID.

    Holds a single X11 display connection, reopened transparently if it drops.
    All failures are swallowed and reported as ``None`` so icon resolution can
    fall through to other strategies.
    """

    def __init__(self) -> None:
        self._display = None
        self._atoms: dict = {}
        self._unavailable = False   # True once we know X11/python-xlib is unusable

    # ── Public API ──────────────────────────────────────────────────────────

    def read_icon(self, pid: int, resource_class: str = ""):
        """Return a QImage of the largest embedded icon for *pid*, or None.

        Falls back to matching by WM_CLASS == *resource_class* when no window
        carries a matching `_NET_WM_PID`.
        """
        if self._unavailable or not pid:
            return None
        try:
            disp = self._ensure_display()
            if disp is None:
                return None
            window = self._find_window(disp, pid, resource_class)
            if window is None:
                return None
            return self._read_net_wm_icon(disp, window)
        except Exception as exc:
            logger.debug("X11 icon read failed (pid=%s): %s", pid, exc)
            # A broken connection won't recover on its own — drop it so the next
            # call reopens rather than raising repeatedly.
            self._display = None
            return None

    # ── Internal ────────────────────────────────────────────────────────────

    def _ensure_display(self):
        if self._display is not None:
            return self._display
        if not os.environ.get("DISPLAY"):
            self._unavailable = True
            return None
        try:
            from Xlib import display
        except ImportError:
            logger.info("python-xlib not installed — embedded window icons disabled")
            self._unavailable = True
            return None
        disp = display.Display()
        self._atoms = {
            "pid":   disp.intern_atom("_NET_WM_PID"),
            "icon":  disp.intern_atom("_NET_WM_ICON"),
            "list":  disp.intern_atom("_NET_CLIENT_LIST"),
        }
        self._display = disp
        return disp

    def _find_window(self, disp, pid: int, resource_class: str):
        from Xlib import X
        from Xlib.Xatom import CARDINAL

        root = disp.screen().root
        prop = root.get_full_property(self._atoms["list"], X.AnyPropertyType)
        if prop is None:
            return None

        fallback = None
        for wid in prop.value:
            win = disp.create_resource_object("window", wid)
            wm_pid = win.get_full_property(self._atoms["pid"], CARDINAL)
            if wm_pid is not None and wm_pid.value and wm_pid.value[0] == pid:
                return win
            if fallback is None and resource_class:
                try:
                    cls = win.get_wm_class()
                except Exception:
                    cls = None
                if cls and resource_class in cls:
                    fallback = win
        return fallback

    def _read_net_wm_icon(self, disp, window):
        from Xlib.Xatom import CARDINAL
        from PyQt6.QtGui import QImage

        prop = window.get_full_property(self._atoms["icon"], CARDINAL)
        if prop is None or not prop.value:
            return None

        data = prop.value
        best = None   # (width, height, pixels)
        i, n = 0, len(data)
        while i + 2 <= n:
            w, h = int(data[i]), int(data[i + 1])
            i += 2
            if w <= 0 or h <= 0 or i + w * h > n:
                break
            pixels = data[i:i + w * h]
            i += w * h
            if best is None or w * h > best[0] * best[1]:
                best = (w, h, pixels)

        if best is None:
            return None

        w, h, pixels = best
        # _NET_WM_ICON stores one 0xAARRGGBB CARDINAL per pixel. Packing them as
        # native-endian uint32 and reading back as QImage.Format_ARGB32 (also
        # native-endian) round-trips correctly regardless of host endianness.
        buf = array.array("I", (int(p) & 0xFFFFFFFF for p in pixels))
        img = QImage(buf.tobytes(), w, h, QImage.Format.Format_ARGB32)
        return img.copy()   # detach from the temporary buffer
