"""Focus navigation between the tile bar and top bar, driven by abstract events.

Owns the focus mode (TILES | TOPBAR) and the top-bar selection index, and
translates navigation events into tile/top-bar moves plus highlight repaint.

Pure interaction logic (application layer): no Qt, no sound backend. It consumes
domain `Event`s and drives the tile/top bars through the `TileFocusView` /
`TopBarView` ports, with cursor feedback via the injected `Feedback` port. The
Qt-key→event translation lives at the edge — the Desktop's eventFilter.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from domain.input.pad_control import PadControl
from domain.input.vocabulary import Event
from domain.navigation import hints
from domain.navigation.bar_views import HintBarView, TileFocusView, TopBarView
from domain.shared.feedback import Cue, Feedback


class _Mode(StrEnum):
    TILES  = "tiles"
    TOPBAR = "topbar"


class FocusNavigator:
    def __init__(
        self,
        tilebar: TileFocusView,
        topbar: TopBarView,
        on_tile_menu: Callable[[], None],
        feedback: Feedback,
        gamepad: PadControl | None = None,
        hint_bar: HintBarView | None = None,
    ) -> None:
        self._tilebar      = tilebar
        self._topbar       = topbar
        self._on_tile_menu = on_tile_menu   # Event.ACTIONS (Y) in tiles → tile popover
        self._feedback     = feedback
        self._gamepad      = gamepad
        self._hint_bar     = hint_bar
        self._mode         = _Mode.TILES
        self._topbar_index = 0

    # ── Queries (for the Desktop eventFilter) ────────────────────────────────

    @property
    def in_tiles(self) -> bool:
        return self._mode == _Mode.TILES

    # ── Navigation ───────────────────────────────────────────────────────────

    def handle_pad(self, event: str) -> None:
        if self._mode == _Mode.TILES:
            if event == Event.LEFT:
                if self._tilebar.move(-1):
                    self._feedback.play(Cue.CURSOR)
                self._sync_hints()   # the [＋] tile has its own hint set
            elif event == Event.RIGHT:
                if self._tilebar.move(+1):
                    self._feedback.play(Cue.CURSOR)
                self._sync_hints()
            elif event == Event.UP and self._topbar.count:
                self._mode = _Mode.TOPBAR
                self._topbar_index = 0
                self._moved()
            elif event == Event.SELECT:
                self._tilebar.select_current()
            elif event == Event.CLOSE:
                self._on_tile_menu()
            elif event == Event.ESCAPE_HOME and self._gamepad is not None:
                self._gamepad.trigger_home()

        elif self._mode == _Mode.TOPBAR:
            if event == Event.LEFT:
                self._topbar_index = (self._topbar_index - 1) % self._topbar.count
                self._moved()
            elif event == Event.RIGHT:
                self._topbar_index = (self._topbar_index + 1) % self._topbar.count
                self._moved()
            elif event in (Event.DOWN, Event.CANCEL):
                self._mode = _Mode.TILES
                self._moved()
            elif event == Event.SELECT:
                self._topbar.trigger(self._topbar_index)

    def render(self) -> None:
        """Repaint the focus highlight across the tile bar and top bar, and sync
        the bottom hint bar to the current screen."""
        in_tiles = self._mode == _Mode.TILES
        self._tilebar.set_focused(in_tiles)
        self._topbar.set_selected(self._topbar_index if not in_tiles else None)
        self._sync_hints()

    def _sync_hints(self) -> None:
        """Push the hint set for the current screen to the hint bar (if wired).

        Within the tiles row the [＋] add tile gets its own set (no "Actions"),
        so the bar reflects which kind of tile is focused, not just the mode."""
        if self._hint_bar is None:
            return
        if self._mode == _Mode.TILES:
            tiles = hints.TILES_ADD if self._tilebar.current_is_add() else hints.TILES
            self._hint_bar.show_hints(tiles)
        else:
            self._hint_bar.show_hints(hints.TOPBAR)

    def _moved(self) -> None:
        self.render()
        self._feedback.play(Cue.CURSOR)

    # ── Mouse hover (delegated from the Desktop slots) ───────────────────────

    def hover_tiles(self) -> None:
        """Pointer entered a tile: take focus into the tile bar."""
        if self._mode != _Mode.TILES:
            self._mode = _Mode.TILES
            self._topbar.set_selected(None)
            self._tilebar.set_focused(True, scroll=False)
        # Always re-sync: hovering between tiles (e.g. onto the [＋]) changes the
        # hint set even when the mode was already TILES.
        self._sync_hints()
        self._feedback.play(Cue.CURSOR)

    def hover_topbar(self, idx: int) -> None:
        """Pointer entered top-bar button *idx*."""
        if self._mode != _Mode.TOPBAR or self._topbar_index != idx:
            self._mode = _Mode.TOPBAR
            self._topbar_index = idx
            self._moved()

    def focus_tiles(self) -> None:
        """Force tiles mode without repaint/sound (before showing a popover)."""
        self._mode = _Mode.TILES

    def focus_topbar(self) -> None:
        """Return focus to the top bar and repaint (e.g. after closing a dialog)."""
        self._mode = _Mode.TOPBAR
        self.render()
