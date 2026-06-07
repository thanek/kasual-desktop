"""Domain model for a configured, launchable application.

Pure Python — no Qt, no I/O. Built by ``system.app_config`` from a ``.desktop``
file and consumed by the Desktop / TileBar / AppManager. Replaces the loose
``dict`` that used to carry these fields around with stringly-typed keys.
"""

import os
from dataclasses import dataclass, field
from collections.abc import Mapping

# Recall-menu triggers (how BTN_MODE behaves once the app is foreground). Kept as
# plain strings so the domain stays free of the input/gamepad framework; the
# GamepadWatcher uses the same literals.
TRIGGER_CLICK   = "BTN_MODE_CLICK"
TRIGGER_HOLD_1S = "BTN_MODE_HOLD_1S"


@dataclass(frozen=True)
class App:
    """An app tile definition. Immutable; one per ``.desktop`` entry."""

    name:                 str
    command:              str
    args:                 tuple[str, ...]   = ()
    icon:                 str | None        = None   # qtawesome glyph (X-Kasual-Icon)
    icon_theme:           str | None        = None   # themed Icon name (freedesktop)
    color:                str               = "#2e3440"
    recall_menu_trigger:  str               = TRIGGER_CLICK
    launch_hide_grace_ms: int               = 0
    env:                  Mapping[str, str] = field(default_factory=dict)

    @property
    def command_basename(self) -> str:
        """Lowercased basename of the command — used to match KWin windows
        (resourceClass / desktopFile) back to this app."""
        return os.path.basename(self.command).lower()
