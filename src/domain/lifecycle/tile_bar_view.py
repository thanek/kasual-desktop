"""The tile bar as the lifecycle touches it — status display and window presence."""

from typing import Protocol


class TileBarView(Protocol):
    """The tile bar as the lifecycle touches it (TileBar): running-status display
    and dynamic-window presence queries. A narrower role-interface than
    navigation's TileFocusView (ISP); TileBar satisfies both."""

    def set_static_closing(self, idx: int) -> None: ...
    def refresh_status(self) -> None: ...
    def has_dynamic_window(self, window_id: str) -> bool: ...
