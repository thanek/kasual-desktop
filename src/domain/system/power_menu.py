"""The Power split-button logic — execute a power action, sticky last-choice (§7.10).

The Home Overlay's Power card shows one default action; ``A`` runs it, and the
dropdown (``Y``) lets the user pick another. Picking *is* using: the chosen action
runs and becomes the new default — but the default only changes once the
**confirmation is accepted**, so a cancelled (``No`` / ``B``) confirm never
re-points the favourite. That "persist only on confirmed execution" rule is pure
domain, kept here and tested without Qt.

The confirm flow itself is injected (the same ``(action_key, on_confirmed)``
callback the :class:`~domain.system.runner.ActionRunner` uses), so this stays free
of the dialog and of any adapter.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.system.actions import ACTIONS, POWER_ACTIONS, ActionDeps
from domain.system.power_preference import PowerPreference


class PowerMenu:
    """Runs power actions and remembers the last confirmed one as the default."""

    def __init__(
        self,
        deps: ActionDeps,
        prefs: PowerPreference,
        confirm: Callable[[str, Callable[[], None]], None],
    ) -> None:
        self._deps = deps
        self._prefs = prefs
        self._confirm = confirm

    def default_key(self) -> str:
        """The current default power action (what ``A`` on the card triggers)."""
        return self._prefs.default()

    def activate_default(self) -> None:
        """Run the default power action — the ``A``-on-the-card happy path."""
        self.select(self._prefs.default())

    def select(self, action_key: str) -> None:
        """Run *action_key*, persisting it as the new default once confirmed.

        Persisting happens inside the confirmed-execution path (before the effect,
        so it sticks even for Shut Down, which never returns), so a cancelled
        confirm leaves the previous default untouched (§7.10 rule 3)."""
        if action_key not in POWER_ACTIONS:
            raise ValueError(f"not a power action: {action_key!r}")
        action = ACTIONS[action_key]

        def execute() -> None:
            self._prefs.set_default(action_key)
            action.effect(self._deps)

        # Power actions all confirm; keep the immediate branch for generality.
        if action.needs_confirmation:
            self._confirm(action_key, execute)
        else:
            execute()
