"""An open top-level window, and the rules relating windows to our apps.

`Window` is a pure value object — the compositor-agnostic view of an open window
(the KWin/D-Bus dict→Window translation stays in the infrastructure adapter).
The matching rules ("does this window belong to that app?", "which recall
trigger does a window inherit?") survive a rewrite to another compositor, so
they live here rather than in the tile bar widget.
"""

import os
from collections.abc import Callable, Mapping, Sequence
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


def external_windows(
    windows:               Sequence[Window],
    apps:                  Sequence[App],
    owned_by_running_group: Callable[[Window], bool],
) -> list[Window]:
    """Windows that deserve their own dynamic tile — those NOT already shown as a
    static app tile, in their original order.

    A window is *managed* (and so excluded) when it belongs to a running app's
    process group or is identifiable as one of our apps; everything else is
    external. A window with no pid (``pid == 0``) is always external — KWin gave
    us nothing to attribute it to, so we never fold it into a static tile even
    if its class happens to match.

    ``owned_by_running_group`` answers the process-group question (the
    ``os.getpgid`` read is infrastructure, injected like ``parent_of`` below).
    """
    def managed(w: Window) -> bool:
        if w.pid == 0:
            return False
        return owned_by_running_group(w) or any(w.matches_app(app) for app in apps)

    return [w for w in windows if not managed(w)]


def app_window_present(
    windows:    Sequence[Window],
    app:        App,
    owned_pids: set[int],
) -> bool:
    """True if a just-launched *app* already has a mapped window — matched either
    by process subtree (the window's pid is among *owned_pids*, the launch and
    its descendants) or by app identity (``matches_app``). Each key covers cases
    the other misses: forwarder launchers (e.g. ``steam steam://...``) show a
    window under an unrelated pid but a matching class, while a bootstrap window
    may carry the right pid before its class is set. The /proc subtree expansion
    that fills *owned_pids* is infrastructure, computed by the caller."""
    return any(w.pid in owned_pids or w.matches_app(app) for w in windows)


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
