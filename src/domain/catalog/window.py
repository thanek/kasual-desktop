"""An open top-level window — the compositor-agnostic value object. The window-list
rules that build on it live in :mod:`domain.catalog.window_rules`."""

import os
from dataclasses import dataclass

from domain.catalog.app import App


@dataclass(frozen=True)
class Window:
    id:             str
    title:          str
    pid:            int  = 0
    active:         bool = False
    fullscreen:     bool = False
    covers_screen:  bool = False
    desktop_file:   str  = ""   # freedesktop desktopFileName (may include ".desktop")
    resource_class: str  = ""   # X11/Wayland app id

    @property
    def holds_screen(self) -> bool:
        """Declared fullscreen, or simply sized to cover the screen — which is how
        a game that never asked shows up."""
        return self.fullscreen or self.covers_screen

    def matches_app(self, app: App) -> bool:
        """True if this window belongs to *app*, matching the resourceClass or the
        desktopFile basename against the app's identity keys. Both window keys,
        since each handles cases the other misses (e.g. Steam self-relaunching)."""
        keys = app.window_match_keys
        rc   = self.resource_class.lower()
        df   = os.path.splitext(self.desktop_file.lower())[0]
        return rc in keys or df in keys
