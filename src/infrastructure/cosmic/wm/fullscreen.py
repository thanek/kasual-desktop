"""Fullscreen for the app in front, which cosmic-comp will not grant itself.

Proton sizes a game's window to the display without ever setting
``_NET_WM_STATE_FULLSCREEN``, and cosmic-comp neither applies that resize nor
offers a fullscreen request of its own (see :mod:`.protocol`) — so the game sits in
a window off the corner of the screen. Its X11 window manager does honour one.
"""

from __future__ import annotations

import logging
import time

from collections.abc import Sequence

from infrastructure.cosmic.wm.toplevels import Toplevel
from infrastructure.cosmic.wm.xwayland import X11Window, XWaylandWindows

logger = logging.getLogger(__name__)

_SETTLE_S = 2.0
_RETRY_S = 5.0
_ATTEMPTS = 5


class ForegroundFullscreen:
    """Gives the screen to the app Kasual Desktop put in front, where COSMIC will
    not."""

    def __init__(self, xwayland: XWaylandWindows) -> None:
        self._xwayland = xwayland
        self._in_front = False
        self._first_seen: dict[int, float] = {}
        self._asks: dict[int, tuple[int, float]] = {}

    def screen_given_to_app(self) -> None:
        if self._in_front:
            return
        self._start_asking_afresh()
        self._in_front = True
        logger.info("the screen is an app's now")

    def screen_taken_back(self) -> None:
        if not self._in_front:
            return
        self._in_front = False
        logger.info("the screen is Kasual Desktop's again")

    def apply(self, toplevels: Sequence[Toplevel],
              x11: Sequence[X11Window]) -> None:
        if not self._in_front:
            return
        self._forget_closed_windows(x11)
        window = self._xwayland.focused_window(x11)
        if window is None or not _wants_the_screen(window):
            return
        owner = _activated_toplevel_of(toplevels, window)
        if owner is None or not self._ask_is_due(window.window_id):
            return
        logger.info("%r (%s) has the screen but not COSMIC's fullscreen — asking "
                    "for it", owner.title, owner.app_id)
        self._xwayland.ask_fullscreen(window)

    def _start_asking_afresh(self) -> None:
        """A game minimized out of its fullscreen has to be put back into it."""
        self._first_seen.clear()
        self._asks.clear()

    def _forget_closed_windows(self, x11: Sequence[X11Window]) -> None:
        live = {w.window_id for w in x11}
        self._first_seen = {w: t for w, t in self._first_seen.items() if w in live}
        self._asks = {w: a for w, a in self._asks.items() if w in live}

    def _ask_is_due(self, window_id: int) -> bool:
        """Whether this window is owed an ask now, counting it if it is."""
        now = time.monotonic()
        first_seen = self._first_seen.setdefault(window_id, now)
        if now - first_seen < _SETTLE_S:
            return False
        asks, last = self._asks.get(window_id, (0, 0.0))
        if asks >= _ATTEMPTS or (asks and now - last < _RETRY_S):
            return False
        self._asks[window_id] = (asks + 1, now)
        return True


def _wants_the_screen(window: X11Window) -> bool:
    """A splash pins its size and a dialog is nobody's fullscreen candidate."""
    return (not window.fullscreen and window.ordinary
            and (window.resizable or window.covers_screen))


def _activated_toplevel_of(toplevels: Sequence[Toplevel],
                           window: X11Window) -> Toplevel | None:
    """By class only: a game and its splash share a title, and the question is
    which app COSMIC has in front, not which window."""
    return next((t for t in toplevels
                 if t.activated and not t.minimized and t.app_id in window.classes),
                None)
