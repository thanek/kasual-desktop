"""Gamepad control hints shown along the bottom of the Desktop.

Labels are English source strings harvested by pylupdate6 from the literal
``translate("HintBar", ...)`` calls at import time and re-translated at render,
so those calls must stay literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.shared.i18n import translate


class Direction(StrEnum):
    """A directional input."""

    UP    = "up"
    DOWN  = "down"
    LEFT  = "left"
    RIGHT = "right"


class Button(StrEnum):
    """A gamepad button."""

    A     = "a"
    B     = "b"
    Y     = "y"
    START = "start"
    HOME  = "home"
    LB    = "lb"
    RB    = "rb"
    LT    = "lt"
    RT    = "rt"


@dataclass(frozen=True)
class ButtonHint:
    """One button paired with what it does on the current screen."""

    button: Button
    label:  str   # source string, re-translated at render


@dataclass(frozen=True)
class Hints:
    """The hint bar for one screen."""

    directions: tuple[Direction, ...]
    overlay:    ButtonHint
    actions:    tuple[ButtonHint, ...]
    nav_label:  str = "Navigate"
    bumpers:    tuple[ButtonHint, ...] = ()
    triggers:   tuple[ButtonHint, ...] = ()
    # A second directional cluster, so a screen whose two axes differ (slider:
    # ↕ picks, ◄► adjusts) isn't misread under one shared label.
    adjust:       tuple[Direction, ...] = ()
    adjust_label: str = "Adjust"


_NAVIGATE = translate("HintBar", "Navigate")
_ADJUST   = translate("HintBar", "Adjust")
_MOVE     = translate("HintBar", "Move")

_SECTION = ButtonHint(Button.LB, translate("HintBar", "Section")), \
           ButtonHint(Button.RB, translate("HintBar", "Section"))
_VOLUME  = ButtonHint(Button.LT, translate("HintBar", "Volume")), \
           ButtonHint(Button.RT, translate("HintBar", "Volume"))

_HOME_MENU = ButtonHint(Button.HOME, translate("HintBar", "Show/Hide menu"))

TILES = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.UP),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Actions")),
    ),
)

TILES_ADD = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.UP),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
    ),
)

MOVE = Hints(
    directions=(Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Confirm")),
        ButtonHint(Button.B, translate("HintBar", "Cancel")),
    ),
    nav_label=_MOVE,
)

TOPBAR = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
    ),
)

TOPBAR_POWER = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Options")),
    ),
)

OVERLAY_MENU = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Back")),
    ),
)

TILE_POPOVER = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Close menu")),
        ButtonHint(Button.B, translate("HintBar", "Back")),
    ),
)

TILE_SETTINGS = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Cancel")),
    ),
    bumpers=_SECTION,
)

ADD_APP = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Cancel")),
    ),
    bumpers=_SECTION,
)

CONFIRM = Hints(
    directions=(Direction.LEFT, Direction.RIGHT),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Cancel")),
    ),
)

NOTIFICATIONS = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
)

CONFIGURATION = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
)

NETWORK = Hints(
    directions=(),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
)

# ── Home Overlay — zoned hint bars ───────────────────────────────────────────

# No A: sliders commit live.
OVERLAY_QUICK = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    nav_label=_NAVIGATE,
    adjust=(Direction.LEFT, Direction.RIGHT),
    adjust_label=_ADJUST,
    bumpers=_SECTION,
    triggers=_VOLUME,
)

OVERLAY_ACTIONS = Hints(
    directions=(Direction.UP, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    bumpers=_SECTION,
    triggers=_VOLUME,
)

OVERLAY_HEADER = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    bumpers=_SECTION,
    triggers=_VOLUME,
)

# Only the header's Power button opens a chooser on Y — the other header
# buttons (Network, Notifications) have no such secondary action.
OVERLAY_HEADER_POWER = Hints(
    directions=(Direction.LEFT, Direction.RIGHT, Direction.DOWN),
    overlay=_HOME_MENU,
    actions=(
        ButtonHint(Button.A, translate("HintBar", "Select")),
        ButtonHint(Button.Y, translate("HintBar", "Options")),
        ButtonHint(Button.B, translate("HintBar", "Close")),
    ),
    bumpers=_SECTION,
    triggers=_VOLUME,
)
