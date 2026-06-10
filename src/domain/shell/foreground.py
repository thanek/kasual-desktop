"""Tracks which app/window is currently 'in front' — what BTN_MODE targets.

Pure state, no Qt. Centralises the transitions that used to be scattered as bare
``self._active_context = ...`` assignments in the Desktop, including the
bug-prone 'clear when the app finished / failed to launch' rule.
"""

from domain.catalog.target import AppTarget, Target


class ForegroundState:
    """The single foreground Target (or None when on the bare Desktop)."""

    def __init__(self) -> None:
        self._target: Target | None = None

    @property
    def current(self) -> Target | None:
        return self._target

    def is_idle(self) -> bool:
        """True when nothing is in front (the Desktop itself is foreground)."""
        return self._target is None

    def set(self, target: Target) -> None:
        self._target = target

    def clear(self) -> None:
        self._target = None

    def clear_if_app(self, index: int) -> None:
        """Clear only if the app at *index* is currently in front.

        Used when that app exits or fails to launch: the foreground must drop
        back to the Desktop, but a different target chosen meanwhile must stay.
        """
        t = self._target
        if isinstance(t, AppTarget) and t.index == index:
            self._target = None
