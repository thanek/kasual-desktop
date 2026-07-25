"""The window-management port as the lifecycle drives it (KWinWindowManager)."""

from collections.abc import Callable
from typing import Protocol

from domain.catalog.window import Window
from domain.shared.event_emitter import Unsubscribe


class WindowManager(Protocol):
    """Window management as the lifecycle drives it."""

    def activate_window(self, window_id: str) -> None: ...
    def close_window(self, window_id: str) -> None: ...
    def cached_windows(self) -> list[Window]: ...
    def refresh_now(self) -> None: ...
    def raise_self(self) -> None: ...

    def screen_given_to_app(self) -> None:
        """The Desktop has gone out of an app's way; ``raise_self`` is its opposite.

        Said even when the launch has no window or process to point at — a Steam
        game runs under the client's tree, not the launch's. Compositors that need
        not arrange anything for the app in front do nothing here.
        """

    def raise_windows_for_pid_exact(self, pid: int) -> None: ...
    def activate_windows_for_pids(self, pids: set[int]) -> None: ...
    def minimize_windows_for_pids(self, pids: set[int]) -> None: ...

    def on_windows_updated(
        self, handler: Callable[[list[Window]], None]
    ) -> Unsubscribe: ...
