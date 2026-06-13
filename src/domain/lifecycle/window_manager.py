"""The window-management port as the lifecycle drives it (KWinWindowManager)."""

from collections.abc import Callable
from typing import Protocol

from domain.catalog.window import Window
from domain.shared.event_emitter import Unsubscribe


class WindowManager(Protocol):
    """Window management as the lifecycle drives it (KWinWindowManager).

    ``on_windows_updated`` is framework-agnostic pub/sub (returning an
    ``Unsubscribe`` token) carrying the refreshed window list as domain
    ``Window``s — the compositor's dict shape stays inside the adapter, and no
    Qt signal leaks through the port. The implementation delivers it on the GUI
    thread; this port says nothing about threading."""

    def activate_window(self, window_id: str) -> None: ...
    def close_window(self, window_id: str) -> None: ...
    def cached_windows(self) -> list[Window]: ...
    def refresh_now(self) -> None: ...
    def raise_self(self) -> None: ...   # bring the Kasual Desktop window to the front
    def raise_windows_for_pid_exact(self, pid: int) -> None: ...
    def activate_windows_for_pids(self, pids: set[int]) -> None: ...
    def minimize_windows_for_pids(self, pids: set[int]) -> None: ...

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Unsubscribe: ...
