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


# Source strings for the directional-cluster label (harvested by pylupdate6;
# re-translated at render). "Navigate" is also the default in Hints above.
_NAVIGATE = translate("HintBar", "Navigate")
_ADJUST   = translate("HintBar", "Adjust")


# The home (BTN_MODE) button toggles the overlay menu, so its label reads the
# same on every screen — it opens the menu from the Desktop and dismisses it
# from within the overlay.
_HOME_MENU = ButtonHint(Button.HOME, translate("HintBar", "Show/Hide menu"))

# The main screen: navigate the tiles, open the home overlay, launch the focused
# app, or open its context / management popover.
TILES = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.UP),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A,     translate("HintBar", "Select")),
        ButtonHint(Button.Y,     translate("HintBar", "Actions")),
        ButtonHint(Button.START, translate("HintBar", "Manage")),
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
