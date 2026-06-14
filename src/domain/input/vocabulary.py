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
    ESCAPE_HOME = "escape_home"


class Trigger(StrEnum):
    """How BTN_MODE recalls the Home menu once an app is in the foreground."""

    CLICK   = "BTN_MODE_CLICK"     # fire immediately on press
    HOLD_1S = "BTN_MODE_HOLD_1S"   # require a ~1 s hold
