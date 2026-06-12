"""Gamepad event types — framework-agnostic dataclasses carrying event data.

Replace Qt ``pyqtSignal`` argument types so the domain layer never imports
PyQt. They are intentionally tiny (the bare fact that something happened); add
payload fields here if a consumer ever needs more than the occurrence itself.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BtnModePressed:
    """BTN_MODE (or the Start+Select chord) was activated."""


@dataclass(frozen=True)
class GamepadConnected:
    """A gamepad device was detected and grabbed."""


@dataclass(frozen=True)
class GamepadDisconnected:
    """The active gamepad device was lost (unplugged / read error)."""
