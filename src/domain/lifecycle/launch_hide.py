"""The deferred-hide port: hide the Desktop only once a launched window maps."""

from typing import Protocol


class LaunchHide(Protocol):
    """Deferred hide of the Desktop until a launched app's window maps (DeferredHide)."""

    @property
    def is_armed(self) -> bool: ...
    def arm(self, idx: int) -> None: ...
    def cancel(self) -> None: ...
