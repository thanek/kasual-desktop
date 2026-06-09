"""The shared vocabulary of Kasual's menus.

One value type for every menu entry, and one place naming every menu *word* the
Home Overlay and the tile Popover can show. The composition rules (which words
appear when) live in `home_menu` / `tile_menu`; how each word looks (label, icon)
and what it does (callback) live in the view wiring. This module is just the
glossary — the entries themselves.
"""

from dataclasses import dataclass

# ── Home Overlay entry kinds ─────────────────────────────────────────────────
RETURN_TO_APP     = "return_to_app"
CLOSE_APP         = "close_app"
RETURN_TO_DESKTOP = "return_to_desktop"

# ── Tile Popover entry kinds ─────────────────────────────────────────────────
LAUNCH  = "launch"
RESTORE = "restore"
CLOSE   = "close"


@dataclass(frozen=True)
class MenuEntry:
    """One abstract menu entry: a named *kind*, optionally carrying the target
    *name* (the app/window title) for entries that act on something specific."""

    kind: str
    name: str = ""
