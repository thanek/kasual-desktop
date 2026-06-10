"""Executing a system action — the confirm-gating around the action catalog.

Gates the confirmable actions behind an injected confirmation flow and runs the
rest immediately. The *which actions exist* table lives next door in
:mod:`domain.system.actions`; this owns only the run/confirm decision.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.system.actions import ACTIONS, ActionDeps


class ActionRunner:
    """Executes a system action: gates the confirmable ones behind the injected
    confirmation flow, runs the rest immediately.

    `confirm(action_key, execute)` is supplied by the view — it resolves the
    localized question for the key and shows the dialog, calling `execute` on
    acceptance. Keeping the question text out of here is what lets this stay
    Qt-free.
    """

    def __init__(
        self,
        deps:    ActionDeps,
        confirm: Callable[[str, Callable[[], None]], None],
    ) -> None:
        self._deps    = deps
        self._confirm = confirm

    def run(self, action_key: str) -> None:
        action  = ACTIONS[action_key]
        execute = lambda: action.effect(self._deps)
        if action.needs_confirmation:
            self._confirm(action_key, execute)
        else:
            execute()
