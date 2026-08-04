"""The "Check DRM playback" menu entry — the DRM setup card opened from the Desktop.

The view is injected next to the gate because the card has to join the Desktop's
overlay group, and only the view holds it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from domain.drm.gate import DrmSetupGate
from domain.navigation import hints as home_hints
from domain.shell.open_overlays import OpenOverlays
from infrastructure.common.qt.overlays.drm_setup_overlay import QtDrmSetupView

if TYPE_CHECKING:
    from .hint_bar import HintBar


class DrmCheckController:
    def __init__(
        self,
        gate: DrmSetupGate | None,
        view: QtDrmSetupView | None,
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
        self._open(force=True)

    def ensure(self) -> bool:
        """True when the card went up: a DRM app whose CDM is missing waits for
        the answer instead of starting."""
        return self._open(force=False)

    def _open(self, *, force: bool) -> bool:
        if self._gate is None or self._view is None or self._card is not None:
            return False
        self._gate.ensure(self._forget, force=force)
        self._card = self._view.current
        if self._card is None:
            return False
        self._overlays.register(self._card)
        self._hint_bar.show_hints(home_hints.CONFIRM)
        return True

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
