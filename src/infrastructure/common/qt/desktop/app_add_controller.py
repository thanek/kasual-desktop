"""The [＋] add-app flow — extracted from the Desktop widget.

Opens the starter-list picker for the add tile, persists the chosen candidates
through the :class:`AppAdder`, and adds their tiles live before the [＋].
:meth:`cancel` clears the picker handle explicitly when the overlay group is
dismissed, since the registry tears the widget down without firing its cancel
callback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from domain.catalog.live_catalog import LiveCatalog
from domain.input.pad_control import PadControl
from domain.navigation import hints as home_hints
from domain.provisioning.add_apps import AppAdder
from domain.shared.feedback import Cue, Feedback
from domain.shared.i18n import translate
from domain.shell.open_overlays import OpenOverlays
from infrastructure.common.qt.overlays.onboarding_overlay import OnboardingOverlay

if TYPE_CHECKING:
    from .hint_bar import HintBar
    from .tile_bar import TileBar


class AppAddController:
    """The add-app picker flow: open it, persist a confirmed selection, forget it."""

    def __init__(
        self,
        apps: LiveCatalog,
        app_adder: AppAdder | None,
        gamepad: PadControl,
        feedback: Feedback,
        tilebar: TileBar,
        overlays: OpenOverlays,
        hint_bar: HintBar,
        restore_hints: Callable[[], None],
        on_cdm_app: Callable[[], None] | None = None,
    ) -> None:
        self._apps = apps
        self._app_adder = app_adder
        self._gamepad = gamepad
        self._feedback = feedback
        self._tilebar = tilebar
        self._overlays = overlays
        self._hint_bar = hint_bar
        self._restore_hints = restore_hints
        self._on_cdm_app = on_cdm_app
        self._picker: OnboardingOverlay | None = None

    def show(self) -> None:
        """Open the add-app picker for the [＋] tile: the onboarding overlay,
        reused with the starter list filtered to not-yet-pinned apps. With
        nothing left to add (or no adder wired) it just plays a back cue."""
        if self._app_adder is None or self._picker is not None:
            return
        candidates = self._app_adder.available(self._apps)
        if not candidates:
            self._feedback.play(Cue.EXIT)
            return
        picker = OnboardingOverlay(self._gamepad, self._feedback)
        self._picker = picker
        self._overlays.register(picker)
        picker.present(
            candidates,
            on_confirm=self._on_added,
            on_cancel=self._forget,
            title=translate("Desktop", "Add app"),
        )
        self._hint_bar.show_hints(home_hints.ADD_APP)

    def _on_added(self, chosen) -> None:
        """Persist the chosen candidates and add their tiles live."""
        self._forget()
        if not chosen:
            return
        self._app_adder.add(chosen)
        for candidate in chosen:
            # add() just wrote this candidate to <candidate.key>.desktop — set the
            # same id here so process tracking matches without waiting for a reload.
            self._tilebar.add_app(replace(candidate.app, id=candidate.key))
        self._feedback.play(Cue.SELECT)
        if self._on_cdm_app is not None and any(c.requires_cdm for c in chosen):
            self._on_cdm_app()

    def _forget(self) -> None:
        self._overlays.forget(self._picker)
        self._picker = None
        self._restore_hints()   # restore the tiles-screen hints

    def cancel(self) -> None:
        """Drop the picker handle when the overlay group is dismissed (the
        registry tears the widget down itself, without firing on_cancel)."""
        self._picker = None
