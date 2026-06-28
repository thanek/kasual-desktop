"""Gamepad control hints shown along the bottom of the Desktop.

Which controls do what on each screen (the tile bar vs the top bar) is
interaction knowledge, so it lives here in the navigation domain: the
:class:`~domain.navigation.focus_navigator.FocusNavigator` owns the screen mode
and pushes the matching :class:`Hints` to the ``HintBarView`` port whenever it
changes. Drawing the glyphs and labels is the Qt adapter's concern (the
``HintBar`` widget).

The labels are English source strings re-translated at render time — the same
extraction-marker pattern as :mod:`domain.system.actions`: the literal
``translate("HintBar", "...")`` calls below run at import time (before any
backend is installed) and pass through unchanged so pylupdate6 can harvest them;
the adapter re-translates each stored label when it renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.shared.i18n import translate


class Direction(StrEnum):
    """A directional input depicted in the navigation cluster (left side)."""

    UP    = "up"
    DOWN  = "down"
    LEFT  = "left"
    RIGHT = "right"


class Button(StrEnum):
    """A gamepad button depicted with its own glyph (right side / overlay)."""

    A     = "a"      # BTN_SOUTH — select / launch / confirm
    B     = "b"      # BTN_EAST — cancel / back (hide the overlay)
    Y     = "y"      # the context popover ("actions")
    START = "start"  # the management popover ("manage")
    HOME  = "home"   # BTN_MODE — the home overlay menu
    LB    = "lb"     # BTN_TL — previous overlay section
    RB    = "rb"     # BTN_TR — next overlay section
    LT    = "lt"     # BTN_TL2 / ABS_Z  — global volume −
    RT    = "rt"     # BTN_TR2 / ABS_RZ — global volume +


@dataclass(frozen=True)
class ButtonHint:
    """One button paired with what it does on the current screen."""

    button: Button
    label:  str   # English source string; re-translated by the adapter at render


@dataclass(frozen=True)
class Hints:
    """The hint bar for one screen.

    Directional navigation and the home-overlay button sit on the left; the
    action buttons on the right. ``nav_label`` reads the directional cluster —
    "Navigate" for menus, "Adjust" for a slider — and is re-translated at render.
    """

    directions: tuple[Direction, ...]
    overlay:    ButtonHint
    actions:    tuple[ButtonHint, ...]
    nav_label:  str = "Navigate"
    # UX v2: the Home Overlay switches sections with the bumpers (LB/RB) and
    # offers global volume on the triggers (LT/RT). Empty on the classic screens.
    bumpers:    tuple[ButtonHint, ...] = ()
    triggers:   tuple[ButtonHint, ...] = ()


# Source strings for the directional-cluster label (harvested by pylupdate6;
# re-translated at render). "Navigate" is also the default in Hints above.
_NAVIGATE = translate("HintBar", "Navigate")
_ADJUST   = translate("HintBar", "Adjust")

# The bumpers step between Home Overlay sections (Quick adjust ⇄ Actions ⇄ HUD);
# the triggers nudge global volume regardless of focus. Both clusters carry one
# shared label — the adapter renders the LB/RB and LT/RT glyphs as a pair.
_SECTION = ButtonHint(Button.LB, translate("HintBar", "Section")), \
           ButtonHint(Button.RB, translate("HintBar", "Section"))
_VOLUME  = ButtonHint(Button.LT, translate("HintBar", "Volume")), \
           ButtonHint(Button.RT, translate("HintBar", "Volume"))


# The home (BTN_MODE) button toggles the overlay menu, so its label reads the
# same on every screen — it opens the menu from the Desktop and dismisses it
# from within the overlay.
_HOME_MENU = ButtonHint(Button.HOME, translate("HintBar", "Show/Hide menu"))

# The main screen: navigate the tiles, open the home overlay, launch the focused
# app, or open its single state-dependent menu with Y (§7.3 — Start is freed).
TILES = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.UP),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Actions")),
    ),
)

# The top bar: move along the system-action buttons, drop back to the tiles, or
# trigger the focused button.
TOPBAR = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
    ),
)

# A menu overlay (the Home Overlay, whether over the Desktop or over a running
# app): step through the vertical menu, toggle it with the home button, confirm
# with A, or hide it with B. The home button stays labelled "Menu" — pressing
# BTN_MODE again is what dismisses the menu it summoned.
OVERLAY_MENU = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Back")),
    ),
)

# The tile popover (the single state-dependent menu, §7.3): step through it with
# up/down, activate with A, and dismiss with B *or* Y — Y both opens and closes
# it (a toggle), so the bar advertises that BTN_NORTH closes the menu it opened.
TILE_POPOVER = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Close menu")),
        ButtonHint(Button.B, translate("HintBar", "Back")),
    ),
)

# A slider dialog (volume / brightness): left/right adjusts the value, A confirms
# and closes, B closes without... well, the same — both just close. The home
# button still summons the menu (dismissing the dialog).
SLIDER = Hints(
    directions=(Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Confirm")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    nav_label=_ADJUST,
)

# A confirmation dialog (unpin, close app, etc.): left/right switches between
# Yes/No, A confirms the focused option, B cancels the whole dialog.
CONFIRM = Hints(
    directions=(Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Cancel")),
    ),
)

# The notifications panel: up/down scrolls through the list, A selects the
# focused notification, B / Esc dismisses the panel.
NOTIFICATIONS = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
)

# The network info popup: A activates the connect/disconnect toggle, B closes.
NETWORK = Hints(
    directions=(),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
)

# ── Home Overlay v2 — zoned hint bars (§7.10) ───────────────────────────────────
# The overlay has more than one kind of control, so the bumpers (LB/RB) own the
# section jump and the D-pad stays inside a section. The hint bar swaps between
# these two as focus moves between zones (FocusNavigator drives the swap — same
# mechanism as TILES/TOPBAR).

# Quick adjust: up/down picks a slider, left/right adjusts it live; the triggers
# duplicate volume as an always-at-hand shortcut. No A here — sliders commit live.
OVERLAY_QUICK = Hints(
    directions=(Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    nav_label=_ADJUST,
    bumpers=_SECTION,
    triggers=_VOLUME,
)

# Actions grid: 2D navigation across the action cards; A activates the focused
# card, Y expands a dropdown (the Power split-button), B closes the overlay.
OVERLAY_ACTIONS = Hints(
    directions=(Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Options")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    bumpers=_SECTION,
    triggers=_VOLUME,
)
