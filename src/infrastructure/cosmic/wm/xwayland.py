"""The X11 windows behind COSMIC toplevels: what they are, and what may be asked
of them.

The toplevel protocols carry neither the owning process (:mod:`.pids`) nor any way
to fullscreen a window (:mod:`.fullscreen`); XWayland, which every Proton title runs
as, has both. Without python-xlib or an X server the snapshot is simply empty.
"""

from __future__ import annotations

import logging
import os

from collections.abc import Sequence
from dataclasses import dataclass

from infrastructure.cosmic.wm.toplevels import Toplevel

logger = logging.getLogger(__name__)

_STATE_ADD = 1
_SOURCE_PAGER = 2


@dataclass(frozen=True)
class X11Window:
    classes:       tuple[str, ...]
    title:         str
    pid:           int
    covers_screen: bool = False
    window_id:     int = 0
    fullscreen:    bool = False
    ordinary:      bool = True
    resizable:     bool = True


def match(windows: Sequence[X11Window], toplevel: Toplevel) -> X11Window | None:
    """The X11 window this toplevel is: by class, with the title breaking a tie
    between instances of one app."""
    candidates = [w for w in windows if toplevel.app_id in w.classes]
    if not candidates:
        return None
    titled = [w for w in candidates if w.title == toplevel.title]
    if len(titled) == 1:
        return titled[0]
    return candidates[0] if len(candidates) == 1 else None


class XWaylandWindows:
    """The X11 client list, read through a connection reopened on demand."""

    def __init__(self) -> None:
        self._display = None
        self._atoms: dict = {}
        self._unavailable = False

    def snapshot(self) -> list[X11Window]:
        try:
            display = self._ensure_display()
            if display is None:
                return []
            return self._read(display)
        except Exception as exc:
            logger.debug("XWayland window scan failed: %s", exc)
            self._display = None
            return []

    def focused_window(self, windows: Sequence[X11Window]) -> X11Window | None:
        """The X11 window holding the focus, which ``_NET_ACTIVE_WINDOW`` goes on
        naming after a Wayland surface has taken it — corroborate before trusting."""
        try:
            display = self._ensure_display()
            if display is None:
                return None
            from Xlib import X

            active = display.screen().root.get_full_property(
                self._atoms["active"], X.AnyPropertyType)
            if active is None or not active.value:
                return None
            window_id = int(active.value[0])
            return next((w for w in windows if w.window_id == window_id), None)
        except Exception as exc:
            logger.debug("XWayland focus read failed: %s", exc)
            self._display = None
            return None

    def ask_fullscreen(self, window: X11Window) -> None:
        """Ask the compositor to fullscreen *window*, the way a pager would."""
        try:
            display = self._ensure_display()
            if display is None:
                return
            from Xlib import X, protocol

            target = display.create_resource_object("window", window.window_id)
            message = protocol.event.ClientMessage(
                window=target,
                client_type=self._atoms["state"],
                data=(32, [_STATE_ADD, self._atoms["fullscreen"], 0, _SOURCE_PAGER, 0]),
            )
            display.screen().root.send_event(
                message,
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            display.flush()
        except Exception as exc:
            logger.debug("XWayland fullscreen request failed: %s", exc)
            self._display = None

    def _ensure_display(self):
        if self._display is not None:
            return self._display
        if self._unavailable or not os.environ.get("DISPLAY"):
            self._unavailable = True
            return None
        try:
            from Xlib import display
        except ImportError:
            logger.info("python-xlib not installed — XWayland window PIDs disabled")
            self._unavailable = True
            return None
        disp = display.Display()
        self._atoms = {
            "list":       disp.intern_atom("_NET_CLIENT_LIST"),
            "active":     disp.intern_atom("_NET_ACTIVE_WINDOW"),
            "pid":        disp.intern_atom("_NET_WM_PID"),
            "name":       disp.intern_atom("_NET_WM_NAME"),
            "state":      disp.intern_atom("_NET_WM_STATE"),
            "fullscreen": disp.intern_atom("_NET_WM_STATE_FULLSCREEN"),
            "type":       disp.intern_atom("_NET_WM_WINDOW_TYPE"),
            "normal":     disp.intern_atom("_NET_WM_WINDOW_TYPE_NORMAL"),
        }
        self._display = disp
        return disp

    def _read(self, display) -> list[X11Window]:
        from Xlib import X
        from Xlib.Xatom import CARDINAL

        listing = display.screen().root.get_full_property(
            self._atoms["list"], X.AnyPropertyType)
        if listing is None:
            return []
        outputs = self._outputs(display)
        windows: list[X11Window] = []
        for window_id in listing.value:
            window = display.create_resource_object("window", window_id)
            try:
                pid = window.get_full_property(self._atoms["pid"], CARDINAL)
                if pid is None or not pid.value:
                    continue
                windows.append(X11Window(
                    classes=tuple(window.get_wm_class() or ()),
                    title=self._title(window),
                    pid=int(pid.value[0]),
                    covers_screen=_fills_an_output(window.get_geometry(), outputs),
                    window_id=int(window_id),
                    fullscreen=self._is_fullscreen(window),
                    ordinary=self._is_ordinary(window),
                    resizable=_is_resizable(window.get_wm_normal_hints()),
                ))
            except Exception as exc:   # a window closed mid-scan drops out alone
                logger.debug("XWayland window 0x%x unreadable: %s", window_id, exc)
        return windows

    def _outputs(self, display) -> list[tuple[int, int]]:
        """The monitors, in the pixels an X11 client's geometry is measured in — not
        the X screen, which on two monitors is the bounding box of both."""
        try:
            monitors = display.screen().root.xrandr_get_monitors().monitors
            if monitors:
                return [(m.width_in_pixels, m.height_in_pixels) for m in monitors]
        except Exception as exc:
            logger.debug("RandR monitor query failed: %s", exc)
        screen = display.screen()
        return [(screen.width_in_pixels, screen.height_in_pixels)]

    def _title(self, window) -> str:
        from Xlib import X

        prop = window.get_full_property(self._atoms["name"], X.AnyPropertyType)
        if prop is not None and prop.value:
            value = prop.value
            return (value.decode("utf-8", "replace") if isinstance(value, bytes)
                    else str(value))
        return window.get_wm_name() or ""

    def _is_fullscreen(self, window) -> bool:
        from Xlib import X

        state = window.get_full_property(self._atoms["state"], X.AnyPropertyType)
        return state is not None and self._atoms["fullscreen"] in state.value

    def _is_ordinary(self, window) -> bool:
        from Xlib import X

        if window.get_wm_transient_for() is not None:
            return False
        kind = window.get_full_property(self._atoms["type"], X.AnyPropertyType)
        return kind is None or self._atoms["normal"] in kind.value


def _fills_an_output(geometry, outputs: Sequence[tuple[int, int]]) -> bool:
    return any(geometry.width >= width and geometry.height >= height
               for width, height in outputs)


def _is_resizable(hints) -> bool:
    """A splash pins itself with ``WM_NORMAL_HINTS``, min equal to max."""
    if hints is None:
        return True
    fixed = (hints.min_width and hints.min_width == hints.max_width
             and hints.min_height and hints.min_height == hints.max_height)
    return not fixed
