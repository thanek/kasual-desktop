"""The shared action vocabulary of Kasual Desktop's menus.

One place naming every menu *action* the Home Overlay and the tile Popover can
offer. The composition rules (which actions appear when, with what label/icon)
live in `home` / `tile`, producing `domain.menu.item.MenuItem`s that carry these
as their `action`; the presenter dispatches on them. This module is just the
glossary.
"""

# ── Home Overlay actions ─────────────────────────────────────────────────────
RETURN_TO_APP     = "return_to_app"
CLOSE_APP         = "close_app"
RETURN_TO_DESKTOP = "return_to_desktop"
TOGGLE_HUD        = "toggle_hud"

# ── Tile Popover actions ─────────────────────────────────────────────────────
LAUNCH  = "launch"
RESTORE = "restore"
CLOSE   = "close"

# ── Tile Management Popover actions ──────────────────────────────────────────
MOVE         = "move"
CHANGE_COLOR = "change_color"
PIN          = "pin"      # turn an open-window tile into a persistent app tile
UNPIN        = "unpin"    # remove a persistent app tile from the menu
