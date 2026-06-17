"""An open top-level window — the compositor-agnostic value object.

`Window` is a pure value object — the compositor-agnostic view of an open window
(the KWin/D-Bus dict→Window translation stays in the infrastructure adapter).
The identity rule "does this window belong to that app?" survives a rewrite to
another compositor, so it lives here rather than in the tile bar widget. The
window-list rules that build on it live in :mod:`domain.catalog.window_rules`.
"""

import os
from dataclasses import dataclass

from domain.catalog.app import App


@dataclass(frozen=True)
class Window:
    id:             str
    title:          str
    pid:            int  = 0
    active:         bool = False
    desktop_file:   str  = ""   # freedesktop desktopFileName (may include ".desktop")
    resource_class: str  = ""   # X11/Wayland app id

    def matches_app(self, app: App) -> bool:
        """True if this window belongs to *app* by identity, via either key:
        the resourceClass or the desktopFile basename matched against the app's
        identity keys. Two window keys because each handles cases the other misses
        (e.g. Steam self-relaunching loses one but keeps the other); the app side
        is usually its command basename but a Steam game tile narrows it to its
        own ``steam_app_<id>`` so games don't all share the ``steam`` identity."""
        keys = app.window_match_keys
        rc   = self.resource_class.lower()
        df   = os.path.splitext(self.desktop_file.lower())[0]
        return rc in keys or df in keys
