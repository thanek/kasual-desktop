"""Focus navigation between the tile bar and top bar, driven by pad/keyboard.

Owns the focus mode ("tiles" | "topbar") and the top-bar selection index, and
translates navigation events into tile/top-bar moves plus highlight repaint.
Extracted from the Desktop so this input-routing logic is unit-testable in
isolation from the layer-shell window.
"""

from collections.abc import Callable

from PyQt6.QtCore import Qt

from audio import sound_player
from .tile_bar import TileBar
from .topbar import TopBar


class FocusNavigator:
    # Keyboard keys mapped to the navigation events the pad emits, so a keyboard
    # can drive the same handler stack (injected via the gamepad).
    _KEY_MAP = {
        Qt.Key.Key_Left:   "left",
        Qt.Key.Key_Right:  "right",
        Qt.Key.Key_Up:     "up",
        Qt.Key.Key_Down:   "down",
        Qt.Key.Key_Return: "select",
        Qt.Key.Key_Enter:  "select",
        Qt.Key.Key_Escape: "cancel",
        Qt.Key.Key_Q:      "close",
    }

    def __init__(
        self,
        tilebar:      TileBar,
        topbar:       TopBar,
        on_tile_menu: Callable[[], None],
    ) -> None:
        self._tilebar      = tilebar
        self._topbar       = topbar
        self._on_tile_menu = on_tile_menu   # "close" in tiles → context popover
        self._mode         = "tiles"        # "tiles" | "topbar"
        self._topbar_index = 0

    # ── Queries (for the Desktop eventFilter) ────────────────────────────────

    @property
    def in_tiles(self) -> bool:
        return self._mode == "tiles"

    def key_event(self, key: Qt.Key) -> str | None:
        """Translate a Qt key to a navigation event, or None if unmapped."""
        return self._KEY_MAP.get(key)

    # ── Navigation ───────────────────────────────────────────────────────────

    def handle_pad(self, event: str) -> None:
        if self._mode == "tiles":
            if event == "left":
                if self._tilebar.move(-1):
                    sound_player.play("cursor")
            elif event == "right":
                if self._tilebar.move(+1):
                    sound_player.play("cursor")
            elif event == "up" and self._topbar.count:
                self._mode = "topbar"
                self._topbar_index = 0
                self._moved()
            elif event == "select":
                self._tilebar.select_current()
            elif event == "close":
                self._on_tile_menu()

        elif self._mode == "topbar":
            if event == "left":
                self._topbar_index = (self._topbar_index - 1) % self._topbar.count
                self._moved()
            elif event == "right":
                self._topbar_index = (self._topbar_index + 1) % self._topbar.count
                self._moved()
            elif event in ("down", "cancel"):
                self._mode = "tiles"
                self._moved()
            elif event == "select":
                self._topbar.trigger(self._topbar_index)

    def render(self) -> None:
        """Repaint the focus highlight across the tile bar and top bar."""
        in_tiles = self._mode == "tiles"
        self._tilebar.set_focused(in_tiles)
        self._topbar.set_selected(self._topbar_index if not in_tiles else None)

    def _moved(self) -> None:
        self.render()
        sound_player.play("cursor")

    # ── Mouse hover (delegated from the Desktop slots) ───────────────────────

    def hover_tiles(self) -> None:
        """Pointer entered a tile: take focus into the tile bar."""
        if self._mode != "tiles":
            self._mode = "tiles"
            self._topbar.set_selected(None)
            self._tilebar.set_focused(True, scroll=False)
        sound_player.play("cursor")

    def hover_topbar(self, idx: int) -> None:
        """Pointer entered top-bar button *idx*."""
        if self._mode != "topbar" or self._topbar_index != idx:
            self._mode = "topbar"
            self._topbar_index = idx
            self._moved()

    def focus_tiles(self) -> None:
        """Force tiles mode without repaint/sound (before showing a popover)."""
        self._mode = "tiles"

    def focus_topbar(self) -> None:
        """Return focus to the top bar and repaint (e.g. after closing a dialog)."""
        self._mode = "topbar"
        self.render()
