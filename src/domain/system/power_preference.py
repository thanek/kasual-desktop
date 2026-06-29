"""The persisted 'favourite' power action — the Power split-button's memory.

The single source of truth for which power action (Sleep / Restart / Shut Down)
is the default: the one ``A`` triggers on the Home Overlay's Power card and the
one the top-bar Power button performs (§7.10). A tiny scalar preference, so it is
its own narrow port rather than a general settings bag; the concrete adapter
persists it under the cross-platform config root.
"""

from typing import Protocol


class PowerPreference(Protocol):
    """Reads/writes the default power action key (one of :data:`POWER_ACTIONS`)."""

    def default(self) -> str:
        """The current default power-action key; falls back to Sleep if unset."""
        ...

    def set_default(self, action_key: str) -> None:
        """Persist *action_key* as the new default (ignored if not a power action)."""
        ...
