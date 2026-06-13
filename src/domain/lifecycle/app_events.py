"""App-lifecycle event types — framework-agnostic dataclasses carrying event data.

Replace Qt ``pyqtSignal`` argument types so the domain layer never imports
PyQt. They carry the app index (and, for a failed launch, the error) — the
minimum a consumer needs to react; add payload fields here if that ever grows.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppStarted:
    """A configured app (by index) was successfully spawned."""

    idx: int


@dataclass(frozen=True)
class AppFinished:
    """A running app (by index) exited — its whole process group is gone."""

    idx: int


@dataclass(frozen=True)
class AppLaunchFailed:
    """Launching app *idx* failed before any process began (e.g. command
    not found / permission denied)."""

    idx: int
    error: str
