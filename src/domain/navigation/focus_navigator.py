"""Focus navigation between the tile bar and top bar, driven by abstract events."""

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
        on_topbar_menu: Callable[[int], None] | None = None,
    ) -> None:
        self._tilebar      = tilebar
        self._topbar       = topbar
        self._on_tile_menu = on_tile_menu
        self._on_topbar_menu = on_topbar_menu
        self._feedback     = feedback
        self._gamepad      = gamepad
        self._hint_bar     = hint_bar
        self._mode         = _Mode.TILES
        self._topbar_index = 0

    @property
    def in_tiles(self) -> bool:
        return self._mode == _Mode.TILES

    @property
    def topbar_index(self) -> int | None:
        return None if self.in_tiles else self._topbar_index

    def handle_pad(self, event: str) -> None:
        if self._mode == _Mode.TILES:
            if event == Event.LEFT:
                if self._tilebar.move(-1):
                    self._feedback.play(Cue.CURSOR)
                self._sync_hints()
            elif event == Event.RIGHT:
                if self._tilebar.move(+1):
                    self._feedback.play(Cue.CURSOR)
                self._sync_hints()
            elif event in (Event.UP, Event.SECTION_PREV) and self._topbar.count:
                self._mode = _Mode.TOPBAR
                self._topbar_index = self._topbar.default_index
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
            elif event in (Event.DOWN, Event.CANCEL, Event.SECTION_NEXT):
                self._mode = _Mode.TILES
                self._moved()
            elif event == Event.SELECT:
                self._topbar.trigger(self._topbar_index)
            elif event == Event.CLOSE and self._on_topbar_menu is not None:
                self._on_topbar_menu(self._topbar_index)

    def render(self) -> None:
        """Repaint the focus highlight and sync the hint bar to the current screen."""
        in_tiles = self._mode == _Mode.TILES
        self._tilebar.set_focused(in_tiles)
        self._topbar.set_selected(self._topbar_index if not in_tiles else None)
        self._sync_hints()

    def _sync_hints(self) -> None:
        # The [＋] add tile gets its own set (no "Actions").
        if self._hint_bar is None:
            return
        if self._mode == _Mode.TILES:
            tiles = hints.TILES_ADD if self._tilebar.current_is_add() else hints.TILES
            self._hint_bar.show_hints(tiles)
        elif self._topbar.has_menu_at(self._topbar_index):
            self._hint_bar.show_hints(hints.TOPBAR_POWER)
        else:
            self._hint_bar.show_hints(hints.TOPBAR)

    def _moved(self) -> None:
        self.render()
        self._feedback.play(Cue.CURSOR)

    def hover_tiles(self) -> None:
        if self._mode != _Mode.TILES:
            self._mode = _Mode.TILES
            self._topbar.set_selected(None)
            self._tilebar.set_focused(True, scroll=False)
        # Hovering onto the [＋] changes the hint set even within TILES.
        self._sync_hints()
        self._feedback.play(Cue.CURSOR)

    def hover_topbar(self, idx: int) -> None:
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

    def focus_topbar_at(self, idx: int) -> None:
        """Land on a top-bar index without repaint/sound, for a later render()."""
        self._mode = _Mode.TOPBAR
        self._topbar_index = idx
