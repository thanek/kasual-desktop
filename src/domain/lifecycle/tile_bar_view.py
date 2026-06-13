"""The tile bar as the lifecycle touches it — status display and window presence."""

from collections.abc import Sequence
from typing import Protocol

from domain.catalog.window import Window


class TileBarView(Protocol):
    """The tile bar as the lifecycle touches it (TileBar): running-status display
    and dynamic-window presence queries. A narrower role-interface than
    navigation's TileFocusView (ISP); TileBar satisfies both."""

    def set_static_closing(self, idx: int) -> None: ...
    def is_closing(self, idx: int) -> bool: ...
    def refresh_status(self) -> None: ...
    def has_dynamic_window(self, window_id: str) -> bool: ...
    def is_tile_running(self, idx: int, windows: Sequence[Window]) -> bool: ...
