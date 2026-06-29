"""Abstract input vocabulary — the framework-independent Kasual Desktop input
   domain.

The set of navigation/action events the UI reacts to, and the BTN_MODE recall
triggers, as a single source of truth. The gamepad adapter (evdev) *produces*
these; navigation and the overlays *consume* them. `StrEnum` members are real
`str`s, so they flow through the existing pyqtSignal / handler-stack transport
(typed `Callable[[str], None]`) unchanged, and compare equal to the legacy
string literals during migration.
"""

from enum import StrEnum


class Event(StrEnum):
    """A directional / action input event, independent of device or key code."""

    UP         = "up"
    DOWN       = "down"
    LEFT       = "left"
    RIGHT      = "right"
    SELECT     = "select"
    CANCEL     = "cancel"
    CLOSE      = "close"
    MANAGE     = "manage"
    ESCAPE_HOME = "escape_home"

    # UX (Home Overlay, §7.10). Produced by the gamepad adapters now so the
    # zoned overlay can consume them later; until then they fall on an empty
    # handler stack and are no-ops.
    SECTION_PREV = "section_prev"  # LB (BTN_TL) — previous overlay section
    SECTION_NEXT = "section_next"  # RB (BTN_TR) — next overlay section
    VOLUME_DOWN  = "volume_down"   # LT (BTN_TL2 / ABS_Z)  — global volume −
    VOLUME_UP    = "volume_up"     # RT (BTN_TR2 / ABS_RZ) — global volume +
    ACTIONS      = "actions"       # Y (BTN_NORTH) — expand a tile / power dropdown


class Trigger(StrEnum):
    """How BTN_MODE recalls the Home menu once an app is in the foreground."""

    CLICK   = "BTN_MODE_CLICK"     # fire immediately on press
    HOLD_1S = "BTN_MODE_HOLD_1S"   # require a ~1 s hold
