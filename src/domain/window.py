"""An open top-level window, and the rules relating windows to our apps.

`Window` is a pure value object — the compositor-agnostic view of an open window
(the KWin/D-Bus dict→Window translation stays in the infrastructure adapter).
The matching rules ("does this window belong to that app?", "which recall
trigger does a window inherit?") survive a rewrite to another compositor, so
they live here rather than in the tile bar widget.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from domain.app import App
from domain.input import Trigger


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
        command basename. Two keys because each handles cases the other misses
        (e.g. Steam self-relaunching loses one but keeps the other)."""
        cmd = app.command_basename
        rc  = self.resource_class.lower()
        df  = os.path.splitext(self.desktop_file.lower())[0]
        return rc == cmd or df == cmd


def resolve_recall_trigger(
    pid:        int,
    pid_to_app: Mapping[int, App],
    parent_of:  Callable[[int], int | None],
) -> str:
    """Recall trigger a window owned by *pid* should use.

    Walks the process-parent chain (``parent_of`` injected — the /proc read is
    infrastructure) until it reaches a pid owned by one of our apps, and returns
    that app's ``recall_menu_trigger`` — so e.g. a game launched by Steam
    inherits Steam's hold-to-recall. Falls back to CLICK when nothing owns it.
    """
    if pid == 0:
        return Trigger.CLICK
    visited: set[int] = set()
    current = pid
    while current > 1 and current not in visited:
        visited.add(current)
        app = pid_to_app.get(current)
        if app is not None:
            return app.recall_menu_trigger
        parent = parent_of(current)
        if parent is None:
            break
        current = parent
    return Trigger.CLICK
