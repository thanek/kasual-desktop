"""The tile bar and top bar as FocusNavigator drives them.

Moving focus/selection and repainting the highlight. Separate, narrower
role-interfaces than the lifecycle's TileBarView (ISP): TileBar satisfies both.
"""

from typing import Protocol

from domain.navigation.hints import Hints


class TileFocusView(Protocol):
    """The tile bar as focus navigation drives it (TileBar)."""

    def move(self, delta: int) -> bool: ...
    def select_current(self) -> None: ...
    def set_focused(self, focused: bool, scroll: bool = True) -> None: ...
    def current_is_add(self) -> bool: ...


class TileReorderView(Protocol):
    """The tile bar as the move-mode coordinator drives it (TileBar).

    A narrow role-interface for reordering the static app tiles: how many there are,
    which one is focused, swapping two of them on screen, and toggling the move-mode
    visual cue. The parallel persistence is a separate port (TileOrderStore)."""

    def app_tile_count(self) -> int: ...
    def current_app_index(self) -> int: ...
    def swap_app_tiles(self, i: int, j: int) -> None: ...
    def set_move_mode(self, active: bool) -> None: ...


class TopBarView(Protocol):
    """The top bar as focus navigation drives it (TopBar)."""

    @property
    def count(self) -> int: ...
    def set_selected(self, index: int | None) -> None: ...
    def trigger(self, index: int) -> None: ...


class HintBarView(Protocol):
    """The bottom hint bar as focus navigation drives it (HintBar).

    The navigator pushes the :class:`Hints` for the current screen whenever the
    focus mode changes; the adapter renders the glyphs/labels."""

    def show_hints(self, hints: Hints) -> None: ...
