"""A setup card reopened from the Desktop, long after the startup gate ran.

The view is injected next to the gate because the card has to join the Desktop's
overlay group, and only the view holds it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from domain.navigation import hints as home_hints
from domain.setup.gate import SetupGate
from domain.shell.open_overlays import OpenOverlays
from infrastructure.common.qt.overlays.setup_overlay import QtSetupView

if TYPE_CHECKING:
    from .hint_bar import HintBar


class SetupCheckController:
    def __init__(
        self,
        gate: SetupGate | None,
        view: QtSetupView | None,
        overlays: OpenOverlays,
        hint_bar: HintBar,
        restore_hints: Callable[[], None],
    ) -> None:
        self._gate = gate
        self._view = view
        self._overlays = overlays
        self._hint_bar = hint_bar
        self._restore_hints = restore_hints
        self._card = None

    def show(self) -> None:
        """Forced: the startup gate has already had its say, so a user who opens
        this deliberately is owed the answer even when everything is in order."""
        if self._gate is None or self._view is None or self._card is not None:
            return
        self._gate.ensure(self._forget, force=True)
        self._card = self._view.current
        if self._card is None:
            return
        self._overlays.register(self._card)
        self._hint_bar.show_hints(home_hints.CONFIRM)

    def cancel(self) -> None:
        """The overlay registry tears the card down itself, and without running
        its on-done callback."""
        self._card = None

    def _forget(self) -> None:
        if self._card is None:
            return
        self._overlays.forget(self._card)
        self._card = None
        self._restore_hints()
