"""The tile bar and top bar as FocusNavigator drives them.

Moving focus/selection and repainting the highlight. Separate, narrower
role-interfaces than the lifecycle's TileBarView (ISP): TileBar satisfies both.
"""

from typing import Protocol


class TileFocusView(Protocol):
    """The tile bar as focus navigation drives it (TileBar)."""

    def move(self, delta: int) -> bool: ...
    def select_current(self) -> None: ...
    def set_focused(self, focused: bool, scroll: bool = True) -> None: ...


class TopBarView(Protocol):
    """The top bar as focus navigation drives it (TopBar)."""

    @property
    def count(self) -> int: ...
    def set_selected(self, index: int | None) -> None: ...
    def trigger(self, index: int) -> None: ...
