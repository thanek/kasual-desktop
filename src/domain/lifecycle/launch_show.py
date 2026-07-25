"""The deferred-show port: return the Desktop once a launched app's windows unmap."""

from typing import Protocol

from domain.catalog.app import App


class LaunchShow(Protocol):
    """Deferred return of the Desktop once a launched app's last window unmaps,
    without waiting for its process to exit (DeferredShow)."""

    @property
    def is_armed(self) -> bool: ...
    @property
    def has_seen_window(self) -> bool: ...
    def arm(self, app: App) -> None: ...
    def cancel(self) -> None: ...
